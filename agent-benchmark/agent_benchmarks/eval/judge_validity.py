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

The threshold is a gate, not a report: ``passed`` is false when any graded
(non-neutral) degradation's accuracy falls below it (a pair the judge failed to
score counts as misordered), so this can run as a scheduled check against a
stored answer set and fail loudly.

Two things keep an accuracy number from meaning what it looks like, and both are
reported alongside it:

* **A character counter passes most of these.** ``len(answer)`` is not a judge,
  and on the original five variants it scores 1.00 on ``truncate_20``,
  ``strip_code`` and ``shuffle_sentences``. Accuracy on those variants is
  therefore not evidence about the judge. The length-only baseline is computed
  on the same pairs, for free, and printed next to every variant; a judge that
  does not beat it there has shown nothing.
* **A single run at 20 bases cannot resolve the gate.** One base is worth
  1/n accuracy — 0.053 at n=19 — so a variant measured at 0.82 against a 0.80
  threshold is one pair from failing, and run-to-run spread with sampling
  unpinned is about that size. Every variant therefore carries a Wilson 95%
  interval, and when that interval straddles the gate the result is reported as
  inconclusive with the number of bases that would settle it. (Wilson, not a
  percentile bootstrap: the bootstrap has zero width on an all-correct run, so a
  3-pair pass would read as conclusive.)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from agent_benchmarks.eval.degrade import DEGRADATIONS, NEUTRAL_VARIANTS, build_pairs
from agent_benchmarks.eval.stats import _wilson

#: Below this, the judge is not usable for arm comparison. A coin flip is 0.50;
#: 0.80 leaves room for genuinely ambiguous pairs without accepting noise.
DEFAULT_MIN_ACCURACY = 0.80

#: Aggregate points within which a neutral variant counts as "did not move".
#: The aggregate is a weighted mean rounded to 0.1 (weights sum to 5 without
#: grounding), so 2.0 is exactly what one weight-1 dimension moving 10 points
#: produces: a single coarse rubric step on one dimension still counts as no
#: movement, a step on `correctness` (weight 2) or on two dimensions does not.
NEUTRAL_TOLERANCE = 2.0
#: Float slack on that boundary: abs(62.4 - 64.4) is 2.000000000000007.
_TOLERANCE_SLACK = 1e-9

#: Scores an answer. Returns the aggregate 0-100 quality score.
Scorer = Callable[[str, str, str], float]


def _accuracy_ci(values: Sequence[float]) -> Tuple[float, float]:
    """Wilson 95% interval for the mean of per-pair outcomes in {0, 0.5, 1}.

    A percentile bootstrap was used here first and it collapses to zero width
    whenever every outcome is identical, so 3/3 or 20/20 correct came out as
    [1.0, 1.0] and a run that small was reported as a *conclusive* pass. The
    Wilson interval keeps its width at the boundary (20/20 -> [0.84, 1.0],
    19/20 -> [0.76, 0.99]), which is the case a gate has to get right.

    Ties enter as half a success. An outcome in {0, 0.5, 1} has variance at most
    p(1-p) for its mean p, so treating the pairs as Bernoulli makes the interval
    slightly wider than the data needs, never narrower.
    """
    n = len(values)
    if not n:
        return (0.0, 0.0)
    return _wilson(sum(values) / n, n)


#: Search ceiling for `_pairs_for_resolution`; reaching it means "far more pairs
#: than anyone will run", which is reported as such rather than as "on the gate".
PAIRS_SEARCH_LIMIT = 1_000_000


def _pairs_for_resolution(p: float, n: int, gate: float, limit: int = PAIRS_SEARCH_LIMIT) -> Optional[int]:
    """Smallest pair count at which the same accuracy stops straddling the gate.

    Searched on the Wilson interval itself rather than estimated from its
    half-width: near 1.0 the interval is lopsided, and the side facing the gate
    is the one that decides. (A symmetric 1/sqrt(n) estimate asked for 12 pairs
    at 19/20 — fewer than the run already had — when 28 are needed.) Returns
    None when accuracy is exactly on the gate: that accuracy straddles at
    any n, so no count follows; only the next run's accuracy settles it.
    """
    if p == gate:
        return None

    def straddles(m: int) -> bool:
        low, high = _wilson(p, m)
        return low < gate <= high

    if not straddles(n):
        return n
    lo, hi = n, n
    while straddles(hi):
        if hi >= limit:
            # Not "on the gate" — just closer to it than any run will get.
            return limit
        lo, hi = hi, min(limit, hi * 2)
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if straddles(mid):
            lo = mid
        else:
            hi = mid
    return hi


def _move(mean_drop: float) -> str:
    """The padded copy's mean move as printed, and its direction read off the printed figure."""
    move = round(-mean_drop, 1) + 0.0  # + 0.0 turns -0.0 into 0.0
    lean = "rewards" if move > 0 else "penalises" if move < 0 else "neither rewards nor penalises"
    return f"{move:+.1f} ({lean}"


@dataclass
class ValidityRow:
    """One judged pair."""

    base_id: str
    arm: str
    variant: str
    intact_score: Optional[float] = None
    degraded_score: Optional[float] = None
    error: Optional[str] = None
    #: Character counts of the two answers, so the length-only baseline can be
    #: evaluated on exactly the same pairs without re-reading the answer set.
    intact_chars: int = 0
    degraded_chars: int = 0

    @property
    def neutral(self) -> bool:
        """True when the correct outcome is *no movement*, not a win."""
        return self.variant in NEUTRAL_VARIANTS

    @property
    def correct(self) -> Optional[float]:
        """1.0 if ordered right, 0.0 if wrong, 0.5 on a tie, None on error."""
        if self.intact_score is None or self.degraded_score is None:
            return None
        if self.intact_score == self.degraded_score:
            return 0.5
        return 1.0 if self.intact_score > self.degraded_score else 0.0

    @property
    def length_correct(self) -> float:
        """The same call made by ``len(answer)`` alone — the null judge.

        Made on an errored pair too, which the gate counts as misordered, so
        the baseline covers the same pairs as the gate accuracy beside it.
        """
        if self.intact_chars == self.degraded_chars:
            return 0.5
        return 1.0 if self.intact_chars > self.degraded_chars else 0.0

    @property
    def unmoved(self) -> Optional[float]:
        """1.0 when the judge scored both members the same, within tolerance.

        This is the right outcome for a neutral variant, where the degraded copy
        has the same content and only more of it.
        """
        if self.intact_score is None or self.degraded_score is None:
            return None
        return 1.0 if abs(self.intact_score - self.degraded_score) <= NEUTRAL_TOLERANCE + _TOLERANCE_SLACK else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "base_id": self.base_id,
            "arm": self.arm,
            "variant": self.variant,
            "neutral": self.neutral,
            "intact_score": self.intact_score,
            "degraded_score": self.degraded_score,
            "correct": self.correct,
            "length_correct": self.length_correct,
            "intact_chars": self.intact_chars,
            "degraded_chars": self.degraded_chars,
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
    seed: int = 0
    #: The variants asked for, so one that produced no pair at all is still reported.
    variants: List[str] = field(default_factory=list)

    @property
    def scored(self) -> List[ValidityRow]:
        return [r for r in self.rows if r.correct is not None]

    @property
    def graded(self) -> List[ValidityRow]:
        """Scored rows whose correct outcome is "intact wins" — the gate's set."""
        return [r for r in self.scored if not r.neutral]

    @property
    def errors(self) -> List[ValidityRow]:
        return [r for r in self.rows if r.error]

    def per_variant(self) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        # Every variant with a row, so one whose every pair errored still shows up (with n = 0).
        for variant in sorted({r.variant for r in self.rows}):
            subset = [r for r in self.scored if r.variant == variant]
            n_errors = sum(1 for r in self.errors if r.variant == variant)
            n = len(subset)
            d = n or 1
            neutral = variant in NEUTRAL_VARIANTS
            correct = [r.correct or 0.0 for r in subset]
            accuracy = sum(correct) / d
            # The interval is taken over the gate's own view of the pairs, so
            # the two cannot disagree about where the threshold falls.
            gate_values = correct + [0.0] * n_errors
            gate_accuracy = sum(gate_values) / (n + n_errors or 1)
            ci_low, ci_high = _accuracy_ci(gate_values)
            length_accuracy = sum(
                r.length_correct for r in self.rows if r.variant == variant
            ) / (n + n_errors)
            stats: Dict[str, Any] = {
                "n": n,
                "n_errors": n_errors,
                "neutral": neutral,
                "accuracy": accuracy,
                # The gate counts an errored pair as misordered: an unscored pair is not evidence.
                "gate_accuracy": gate_accuracy,
                "accuracy_ci": [ci_low, ci_high],
                "length_accuracy": length_accuracy,
                # Against the number the table prints next to it, over the
                # same pairs: with errored pairs, `accuracy` (errors excluded)
                # can beat the baseline while the displayed gate_accuracy does not.
                "beats_length": gate_accuracy > length_accuracy,
                "tie_rate": sum(1 for r in subset if r.correct == 0.5) / d,
                "mean_drop": sum(
                    (r.intact_score or 0.0) - (r.degraded_score or 0.0) for r in subset
                )
                / d,
                "mean_intact": sum(r.intact_score or 0.0 for r in subset) / d,
                "mean_degraded": sum(r.degraded_score or 0.0 for r in subset) / d,
            }
            if neutral:
                # Graded against "did not move", and the gate ignores it. A
                # judge rewarding the padded copy shows up as unmoved_rate low
                # with accuracy below 0.5.
                stats["unmoved_rate"] = sum(r.unmoved or 0.0 for r in subset) / d
            else:
                stats["straddles_gate"] = ci_low < self.min_accuracy <= ci_high
                stats["bases_for_resolution"] = (
                    _pairs_for_resolution(gate_accuracy, n + n_errors, self.min_accuracy)
                    if stats["straddles_gate"] else None
                )
            out[variant] = stats
        return out

    def summary(self) -> Dict[str, Any]:
        graded = self.graded
        n = len(graded)
        correct = [r.correct or 0.0 for r in graded]
        n_graded_errors = sum(1 for r in self.errors if r.variant not in NEUTRAL_VARIANTS)
        accuracy = sum(correct) / n if n else 0.0
        tie_rate = sum(1 for r in graded if r.correct == 0.5) / n if n else 0.0
        gate_rows = [r for r in self.rows if not r.neutral]
        length_accuracy = (
            sum(r.length_correct for r in gate_rows) / len(gate_rows) if gate_rows else 0.0
        )
        per_variant = self.per_variant()
        gated = {k: v for k, v in per_variant.items() if not v["neutral"]}
        inconclusive = sorted(k for k, v in gated.items() if v["straddles_gate"])
        # A fail is settled by one variant whose whole interval sits under the
        # gate, whatever the others straddle.
        settled_fail = any(v["accuracy_ci"][1] < self.min_accuracy for v in gated.values())
        # A requested variant with no pair (every degradation was a no-op) was
        # not measured: the gate says nothing about it, so a pass cannot be settled.
        measured = {r.variant for r in self.rows}
        unmeasured = sorted(set(self.variants or self.n_noop) - measured)
        return {
            "judge": self.judge,
            # Pooled over the graded variants only; neutral variants have no
            # "intact wins" target and would bias the pool either way.
            "n_pairs": n,
            "n_neutral_pairs": len(self.scored) - n,
            "n_errors": len(self.errors),
            "accuracy": accuracy,
            # The gate's view of the pool (an errored pair counts as wrong), so
            # the printed point estimate sits inside its own interval.
            "gate_accuracy": sum(correct) / (n + n_graded_errors) if (n + n_graded_errors) else 0.0,
            "accuracy_ci": list(_accuracy_ci(correct + [0.0] * n_graded_errors)),
            # The degradation draw this report was built from.
            "seed": self.seed,
            "length_accuracy": length_accuracy,
            "tie_rate": tie_rate,
            "min_accuracy": self.min_accuracy,
            # No pairs scored fails; so does any variant below the gate, which a pooled mean hides.
            "passed": bool(n) and all(v["gate_accuracy"] >= self.min_accuracy for v in gated.values()),
            # A pass whose interval straddles the threshold is not reproducible:
            # the gate cannot tell the configuration from one that fails.
            "conclusive": bool(n) and (not (inconclusive or unmeasured) or settled_fail),
            "inconclusive_variants": inconclusive,
            "unmeasured_variants": unmeasured,
            "per_variant": per_variant,
            "n_noop": dict(sorted(self.n_noop.items())),
            "wall_seconds": self.wall_seconds,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {"summary": self.summary(), "rows": [r.to_dict() for r in self.rows]}

    def format_summary(self) -> str:
        s = self.summary()
        ci = s["accuracy_ci"]
        lines = [
            f"Judge validity — {s['judge']}",
            f"  pairs scored : {s['n_pairs']} graded"
            + (f" + {s['n_neutral_pairs']} neutral" if s["n_neutral_pairs"] else "")
            + (f"  (errors: {s['n_errors']})" if s["n_errors"] else ""),
            f"  accuracy     : {s['gate_accuracy']:.3f}  95% CI [{ci[0]:.3f}, {ci[1]:.3f}]"
            f"   (gate ≥ {s['min_accuracy']:.2f})"
            + (f"  [{s['accuracy']:.3f} with errored pairs left out]" if s["n_errors"] else ""),
            f"  length-only  : {s['length_accuracy']:.3f}   (len(answer) alone — not a judge)",
            f"  tie rate     : {s['tie_rate']:.3f}   (saturated scale if high)",
            f"  no-op pairs  : {sum(s['n_noop'].values())} dropped (degradation left the text unchanged)",
            "",
            f"  {'degradation':20s} {'n':>4s} {'err':>4s} {'gate':>6s} {'95% CI':>13s} "
            f"{'len':>6s} {'ties':>6s} {'drop':>7s} {'intact':>7s} {'damaged':>8s}",
        ]
        for variant, v in s["per_variant"].items():
            flag = "  neutral" if v["neutral"] else ("" if v["beats_length"] else "  <= length")
            vci = v["accuracy_ci"]
            lines.append(
                f"  {variant:20s} {int(v['n']):4d} {int(v['n_errors']):4d} "
                f"{v['gate_accuracy']:6.2f} [{vci[0]:5.2f},{vci[1]:5.2f}] "
                f"{v['length_accuracy']:6.2f} {v['tie_rate']:6.2f} {v['mean_drop']:+7.1f} "
                f"{v['mean_intact']:7.1f} {v['mean_degraded']:8.1f}{flag}"
            )
        for variant in s["unmeasured_variants"]:
            lines.append(f"  {variant:20s} {0:4d}  not measured: no pair, {s['n_noop'].get(variant, 0)} no-op")
        neutral = {k: v for k, v in s["per_variant"].items() if v["neutral"]}
        if neutral:
            lines.append("")
            for variant, v in neutral.items():
                lines.append(
                    f"  {variant}: correct outcome is no movement — "
                    f"unmoved {v['unmoved_rate']:.2f}, mean move {_move(v['mean_drop'])} the longer copy). "
                    "Not gated."
                )
        if s["inconclusive_variants"]:
            lines.append("")
            lines.append("  INCONCLUSIVE — these intervals straddle the gate, so this")
            lines.append("  run cannot tell a pass from a fail on them:")
            for variant in s["inconclusive_variants"]:
                v = s["per_variant"][variant]
                need = v["bases_for_resolution"]
                lines.append(
                    f"    {variant:20s} {v['gate_accuracy']:.2f} vs gate {s['min_accuracy']:.2f}"
                    + (f" — needs {'over ' if need >= PAIRS_SEARCH_LIMIT else '~'}{need} pairs "
                       f"({need / max(1, int(v['n']) + int(v['n_errors'])):.1f}x this run)"
                       if need else " — on the gate exactly; add pairs, no count follows from a zero margin")
                )
        lines.append("")
        result = "PASS" if s["passed"] else "FAIL"
        if not s["n_pairs"]:
            result += " (no graded pair was scored)"
        elif not s["conclusive"]:
            result += " (inconclusive — see above)"
        lines.append("  RESULT: " + result)
        return "\n".join(lines)


def evaluate_pairs(
    scorer: Scorer,
    pairs: Sequence[Dict[str, Any]],
    *,
    judge: str = "unknown",
    min_accuracy: float = DEFAULT_MIN_ACCURACY,
    seed: int = 0,
    progress: Optional[Callable[[int, int], None]] = None,
) -> ValidityReport:
    """Score every pair and report validity.

    The intact answer is scored once per (base_id, arm) and reused across that
    base's variants — the damaged copies are what differ, so re-scoring the
    intact member per variant would multiply the cost for nothing.
    """
    report = ValidityReport(judge=judge, min_accuracy=min_accuracy, seed=seed)
    intact_cache: Dict[tuple, float] = {}
    started = time.time()

    for index, pair in enumerate(pairs, 1):
        row = ValidityRow(
            base_id=pair["base_id"],
            arm=pair.get("arm", ""),
            variant=pair["variant"],
            intact_chars=len(pair["intact"]),
            degraded_chars=len(pair["degraded"]),
        )
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
    variants = list(variants or DEGRADATIONS)
    pairs = build_pairs(
        answers,
        noop=noop,
        n_bases=n_bases,
        seed=seed,
        variants=variants,
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
        scorer, pairs, judge=judge, min_accuracy=min_accuracy, seed=seed, progress=progress
    )
    report.n_noop = noop
    report.variants = variants
    return report
