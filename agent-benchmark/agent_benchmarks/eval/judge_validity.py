# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Discriminative validity of the judge: can it order pairs we already know?

The judge produces 0-100 scores that decide whether a skill ships. Nothing in
the pipeline currently checks that those scores track answer quality at all — a
prompt edit or a model swap can quietly degrade the judge to a coin flip and
every downstream number still looks plausible.

This module closes that hole. It takes real answers, builds pairs whose correct
ordering is known by construction (:mod:`agent_benchmarks.eval.degrade`), and
reports **pairwise accuracy**: the fraction of pairs where the judge scored the
intact answer above its damaged copy. Ties count as 0.5, because a judge that
cannot separate the two has not made the call.

Two failure signatures worth naming, both of which this surfaces:

* **low accuracy** — the judge is ordering by something other than quality.
* **high tie rate** — the judge is saturated at the top of its scale, so good
  and damaged answers land on the same number. This is the common one, and it
  is invisible in a correlation study.

The threshold is a gate, not a report: ``passed`` is false when any
degradation's accuracy falls below it (a pair the judge failed to score counts as
misordered), so this can run as a scheduled check against a stored
answer set and fail loudly.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from agent_benchmarks.eval.degrade import DEGRADATIONS, build_pairs

#: Below this, the judge is not usable for arm comparison. A coin flip is 0.50;
#: 0.80 leaves room for genuinely ambiguous pairs without accepting noise.
DEFAULT_MIN_ACCURACY = 0.80

#: Scores an answer. Returns the aggregate 0-100 quality score.
Scorer = Callable[[str, str, str], float]


@dataclass
class ValidityRow:
    """One judged pair."""

    base_id: str
    arm: str
    variant: str
    intact_score: Optional[float] = None
    degraded_score: Optional[float] = None
    error: Optional[str] = None

    @property
    def correct(self) -> Optional[float]:
        """1.0 if ordered right, 0.0 if wrong, 0.5 on a tie, None on error."""
        if self.intact_score is None or self.degraded_score is None:
            return None
        if self.intact_score == self.degraded_score:
            return 0.5
        return 1.0 if self.intact_score > self.degraded_score else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "base_id": self.base_id,
            "arm": self.arm,
            "variant": self.variant,
            "intact_score": self.intact_score,
            "degraded_score": self.degraded_score,
            "correct": self.correct,
            "error": self.error,
        }


@dataclass
class ValidityReport:
    """Per-variant and overall validity of one judge configuration."""

    judge: str
    rows: List[ValidityRow] = field(default_factory=list)
    min_accuracy: float = DEFAULT_MIN_ACCURACY
    wall_seconds: float = 0.0
    n_noop: Dict[str, int] = field(default_factory=dict)

    @property
    def scored(self) -> List[ValidityRow]:
        return [r for r in self.rows if r.correct is not None]

    @property
    def errors(self) -> List[ValidityRow]:
        return [r for r in self.rows if r.error]

    def per_variant(self) -> Dict[str, Dict[str, float]]:
        out: Dict[str, Dict[str, float]] = {}
        # Every variant with a row, so one whose every pair errored still shows up (with n = 0).
        for variant in sorted({r.variant for r in self.rows}):
            subset = [r for r in self.scored if r.variant == variant]
            n_errors = sum(1 for r in self.errors if r.variant == variant)
            n = len(subset)
            d = n or 1
            out[variant] = {
                "n": n,
                "n_errors": n_errors,
                "accuracy": sum(r.correct or 0.0 for r in subset) / d,
                # The gate counts an errored pair as misordered: an unscored pair is not evidence.
                "gate_accuracy": sum(r.correct or 0.0 for r in subset) / (n + n_errors),
                "tie_rate": sum(1 for r in subset if r.correct == 0.5) / d,
                "mean_drop": sum(
                    (r.intact_score or 0.0) - (r.degraded_score or 0.0) for r in subset
                )
                / d,
                "mean_intact": sum(r.intact_score or 0.0 for r in subset) / d,
                "mean_degraded": sum(r.degraded_score or 0.0 for r in subset) / d,
            }
        return out

    def summary(self) -> Dict[str, Any]:
        scored = self.scored
        n = len(scored)
        accuracy = sum(r.correct or 0.0 for r in scored) / n if n else 0.0
        tie_rate = sum(1 for r in scored if r.correct == 0.5) / n if n else 0.0
        per_variant = self.per_variant()
        return {
            "judge": self.judge,
            "n_pairs": n,
            "n_errors": len(self.errors),
            "accuracy": accuracy,
            "tie_rate": tie_rate,
            "min_accuracy": self.min_accuracy,
            # No pairs scored fails; so does any variant below the gate, which a pooled mean hides.
            "passed": bool(n) and all(v["gate_accuracy"] >= self.min_accuracy for v in per_variant.values()),
            "per_variant": per_variant,
            "n_noop": dict(sorted(self.n_noop.items())),
            "wall_seconds": self.wall_seconds,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {"summary": self.summary(), "rows": [r.to_dict() for r in self.rows]}

    def format_summary(self) -> str:
        s = self.summary()
        lines = [
            f"Judge validity — {s['judge']}",
            f"  pairs scored : {s['n_pairs']}" + (f"  (errors: {s['n_errors']})" if s["n_errors"] else ""),
            f"  accuracy     : {s['accuracy']:.3f}   (gate ≥ {s['min_accuracy']:.2f})",
            f"  tie rate     : {s['tie_rate']:.3f}   (saturated scale if high)",
            f"  no-op pairs  : {sum(s['n_noop'].values())} dropped (degradation left the text unchanged)",
            "",
            f"  {'degradation':20s} {'n':>4s} {'err':>4s} {'acc':>6s} {'gate':>6s} {'ties':>6s} "
            f"{'drop':>7s} {'intact':>7s} {'damaged':>8s}",
        ]
        for variant, v in s["per_variant"].items():
            lines.append(
                f"  {variant:20s} {int(v['n']):4d} {int(v['n_errors']):4d} {v['accuracy']:6.2f} "
                f"{v['gate_accuracy']:6.2f} {v['tie_rate']:6.2f} {v['mean_drop']:+7.1f} "
                f"{v['mean_intact']:7.1f} {v['mean_degraded']:8.1f}"
            )
        lines.append("")
        lines.append("  RESULT: " + ("PASS" if s["passed"] else "FAIL"))
        return "\n".join(lines)


def evaluate_pairs(
    scorer: Scorer,
    pairs: Sequence[Dict[str, Any]],
    *,
    judge: str = "unknown",
    min_accuracy: float = DEFAULT_MIN_ACCURACY,
    progress: Optional[Callable[[int, int], None]] = None,
) -> ValidityReport:
    """Score every pair and report validity.

    The intact answer is scored once per (base_id, arm) and reused across that
    base's variants — the damaged copies are what differ, so re-scoring the
    intact member per variant would multiply the cost for nothing.
    """
    report = ValidityReport(judge=judge, min_accuracy=min_accuracy)
    intact_cache: Dict[tuple, float] = {}
    started = time.time()

    for index, pair in enumerate(pairs, 1):
        row = ValidityRow(base_id=pair["base_id"], arm=pair.get("arm", ""), variant=pair["variant"])
        key = (pair["base_id"], pair.get("arm", ""))
        try:
            if key not in intact_cache:
                intact_cache[key] = float(
                    scorer(pair["library"], pair["question"], pair["intact"])
                )
            row.intact_score = intact_cache[key]
            row.degraded_score = float(
                scorer(pair["library"], pair["question"], pair["degraded"])
            )
        except Exception as exc:  # one bad pair must not lose the whole run
            row.error = f"{type(exc).__name__}: {exc}"[:200]
        report.rows.append(row)
        if progress:
            progress(index, len(pairs))

    report.wall_seconds = time.time() - started
    return report


def judge_scorer(judge: Any) -> Scorer:
    """Adapt a :class:`~agent_benchmarks.eval.judge.Judge` to :data:`Scorer`.

    Ground truth is deliberately not passed: the pair differs only in the
    answer, and a grounded prompt would let the judge score the damaged copy
    against the excerpt rather than judge the answer itself.
    """

    def score(library: str, question: str, answer: str) -> float:
        scores = judge.score_answer(library_name=library, question=question, answer=answer)
        return float(scores["aggregate"])

    return score


def run_validity(
    answers: Sequence[Dict[str, Any]],
    scorer: Scorer,
    *,
    judge: str = "unknown",
    n_bases: int = 20,
    seed: int = 0,
    variants: Optional[Sequence[str]] = None,
    library: str = "the library",
    min_accuracy: float = DEFAULT_MIN_ACCURACY,
    progress: Optional[Callable[[int, int], None]] = None,
) -> ValidityReport:
    """Build degradation pairs from ``answers`` and measure the judge on them."""
    noop: Dict[str, int] = {}
    pairs = build_pairs(
        answers,
        noop=noop,
        n_bases=n_bases,
        seed=seed,
        variants=variants or tuple(DEGRADATIONS),
        library=library,
    )
    if not pairs and noop:
        raise ValueError(f"Every degradation left the answer unchanged (no-op pairs: {noop})")
    if not pairs:
        raise ValueError(
            "No usable answers found — need answers longer than the minimum "
            "length with a question_id and question text"
        )
    report = evaluate_pairs(
        scorer, pairs, judge=judge, min_accuracy=min_accuracy, progress=progress
    )
    report.n_noop = noop
    return report
