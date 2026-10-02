# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Deterministic answer degradations — ground truth for judging the judge.

A judge that reports 0-100 quality scores is only useful if its ordering is
right. Correlating it against another judge cannot show that: two judges can
agree and both be wrong. What can show it is a pair whose correct ordering we
know by construction — an answer and a mechanically damaged copy of the same
answer. The intact member must score higher. If it does not, the judge is not
measuring answer quality.

The degradations here are pure and seeded, so a validity run is reproducible
and costs no LLM calls to build. Each one targets a different failure the judge
must be able to see:

  truncate_20        missing content (the answer stops early)
  strip_code         missing executable detail
  shuffle_sentences  destroyed structure, same facts
  wrong_tools        fluent, confident, wrong technology  <- the hard one
  mismatched_answer  an answer to a different question entirely

``wrong_tools`` is the case that matters most in practice, because it is the
failure mode a documentation agent actually has: the prose stays polished while
the advice becomes unusable. It is also the case judges fail most often, since
they reward fluency.
"""

from __future__ import annotations

import random
import re
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

CODE_BLOCK = re.compile(r"```.*?```", re.S)

#: Minimum answer length (characters) worth degrading. Short answers have too
#: little content for truncation or code-stripping to mean anything.
DEFAULT_MIN_CHARS = 1500


def truncate_20(answer: str, **_: Any) -> str:
    """Keep the first fifth of the answer (at least 200 characters)."""
    return answer[: max(200, len(answer) // 5)]


def strip_code(answer: str, **_: Any) -> str:
    """Remove every fenced code block, leaving a marker behind."""
    return CODE_BLOCK.sub("[code removed]", answer)


def shuffle_sentences(answer: str, rng: Optional[random.Random] = None, **_: Any) -> str:
    """Keep the facts, destroy the order. Needs a seeded rng for reproducibility."""
    if rng is None:
        raise ValueError("shuffle_sentences requires a seeded rng")
    parts = re.split(r"(?<=[.!?])\s+", CODE_BLOCK.sub("", answer))
    rng.shuffle(parts)
    return " ".join(parts)


#: Substitutions that swap a correct technology for a plausible wrong one.
#: Domain-specific by nature — this table covers the Intel performance-tooling
#: domain. Pass ``substitutions=`` to :func:`wrong_tools` for another domain.
WRONG_TOOL_SUBSTITUTIONS: Sequence[tuple[str, str]] = (
    (r"\bperf\b", "gprof"),
    (r"toplev(\.py)?", "valgrind"),
    (r"\bIntel\b", "AMD"),
    (r"\bIPC\b", "MFLOPS"),
    (r"\bVTune\b", "Instruments"),
    (r"\bAVX-?512\b", "3DNow!"),
    (r"\buarch\b", "frontend"),
    (r"\boneAPI\b", "ROCm"),
    (r"\boneTBB\b", "pthreads"),
    (r"\bumask\b", "affinity"),
    (r"\bPMU\b", "sampler"),
)


def wrong_tools(
    answer: str,
    substitutions: Optional[Sequence[tuple[str, str]]] = None,
    **_: Any,
) -> str:
    """Swap correct tool/flag/vendor names for plausible wrong ones."""
    out = answer
    for pattern, replacement in substitutions or WRONG_TOOL_SUBSTITUTIONS:
        out = re.sub(pattern, replacement, out)
    return out


def mismatched_answer(answer: str, other: Optional[str] = None, **_: Any) -> str:
    """Replace the answer with a real answer to a *different* question."""
    if not other:
        raise ValueError("mismatched_answer requires another answer to substitute")
    return other


Degradation = Callable[..., str]

DEGRADATIONS: Dict[str, Degradation] = {
    "truncate_20": truncate_20,
    "strip_code": strip_code,
    "shuffle_sentences": shuffle_sentences,
    "wrong_tools": wrong_tools,
    "mismatched_answer": mismatched_answer,
}


def degrade(
    answer: str,
    variant: str,
    *,
    seed: int = 0,
    other: Optional[str] = None,
) -> str:
    """Apply one named degradation. Pure given ``seed``."""
    if variant not in DEGRADATIONS:
        raise ValueError(f"Unknown degradation '{variant}'; known: {sorted(DEGRADATIONS)}")
    return DEGRADATIONS[variant](answer, rng=random.Random(seed), other=other)


def _answer_pool(answers: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Flatten a run's answers into (question_id, question_text, arm, answer) rows.

    Accepts both the arm-runner shape (``arms: {name: {answer: ...}}``) and the
    legacy two-condition shape (``with_docs``/``without_docs``).
    """
    pool: List[Dict[str, Any]] = []
    for item in answers:
        if not isinstance(item, dict):
            continue
        qid = item.get("question_id")
        qtext = item.get("question_text") or item.get("question")
        if not qid or not qtext:
            continue
        arms = item.get("arms")
        candidates: List[tuple[str, Any]] = []
        if isinstance(arms, dict):
            candidates = list(arms.items())
        else:
            for legacy in ("with_docs", "without_docs"):
                if legacy in item:
                    candidates.append((legacy, item[legacy]))
        for arm, payload in candidates:
            text = (payload or {}).get("answer") if isinstance(payload, dict) else payload
            if isinstance(text, str) and text.strip():
                pool.append({"question_id": qid, "question_text": qtext, "arm": arm, "answer": text})
    return pool


def build_pairs(
    answers: Iterable[Dict[str, Any]],
    *,
    n_bases: int = 20,
    seed: int = 0,
    min_chars: int = DEFAULT_MIN_CHARS,
    variants: Optional[Sequence[str]] = None,
    library: str = "the library",
    noop: Optional[Dict[str, int]] = None,
) -> List[Dict[str, Any]]:
    """Build (intact, degraded) pairs with a known correct ordering.

    One pair per (base answer x variant); ``intact`` must score higher. A
    degradation that left the text unchanged is dropped and counted in ``noop``.
    """
    for name in variants or ():
        if name not in DEGRADATIONS:
            raise ValueError(f"Unknown degradation '{name}'; known: {sorted(DEGRADATIONS)}")
    pool = _answer_pool(answers)
    rng = random.Random(seed)
    rng.shuffle(pool)
    bases = [row for row in pool if len(row["answer"]) > min_chars][:n_bases]

    pairs: List[Dict[str, Any]] = []
    for base in bases:
        # An answer to some other question, for the mismatched_answer variant. Drawn per base:
        # taking the first one gave every base the same substitute.
        others = [r["answer"] for r in pool if r["question_id"] != base["question_id"]]
        other = rng.choice(others) if others else None
        for name in variants or DEGRADATIONS:
            if name == "mismatched_answer" and not other:
                continue
            degraded = DEGRADATIONS[name](base["answer"], rng=random.Random(seed), other=other)
            if degraded == base["answer"]:
                if noop is not None:
                    noop[name] = noop.get(name, 0) + 1
                continue
            pairs.append(
                {
                    "base_id": base["question_id"],
                    "arm": base["arm"],
                    "question": base["question_text"],
                    "library": library,
                    "variant": name,
                    "intact": base["answer"],
                    "degraded": degraded,
                }
            )
    return pairs
