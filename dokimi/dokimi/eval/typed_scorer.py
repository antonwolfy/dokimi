# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Typed-decision baseline arms for the judge-validity gate.

The gate grades a scorer on pairs whose ordering is known, and it already prints
one free reference line — `len(answer)` alone. This module adds a second kind of
reference: a small local model that reads the answer but generates nothing,
scoring each dimension by reading the probabilities of fixed single-token answer
slots in one forward pass.

The point is not to replace the LLM judge. It is to have a floor that reads the
text, so "the judge is no better than a 400M-parameter encoder" shows up as a
number in the gate's own report instead of going unnoticed. How high that
floor sits depends on how much of the answer the arm reads. Measured on
`perf_sonnet` answers (20 bases, 170 pairs, seed 0, laya 0.3.28, checkpoint
revision 7b928d8, length-only 0.613 on the same pairs):

==========================================  ========  ==============  =========
arm                                         accuracy  Wilson 95%      truncated
==========================================  ========  ==============  =========
English, default 512 tokens                    0.537  [0.457, 0.615]    176/190
multilingual, ``--typed-max-len 8192``         0.707  [0.629, 0.774]      0/190
==========================================  ========  ==============  =========

The English arm's point estimate sits below length-only and its interval
reaches 0.615, so "worse than length" is not established at this n. The
multilingual arm reading whole answers is above length-only, which a reviewer
also measured on three other answer sets (0.694-0.781 against 0.615-0.670): the
low English number is mostly what the budget hides, not what the encoder
cannot judge. The judge measured 0.920 on the earlier 176-pair version of this
set (Haiku 4.5, before #52's prompt change). Scores go through the judge's
1-decimal rounding; laya scores are continuous, so that turns near-ties into
ties (English tie rate 0.287).

Read per-variant numbers with the truncation in mind. The English checkpoint's
512-token budget drops the *tail* of ``LIBRARY / QUESTION / ANSWER``. A pair
whose whole edit lies past the budget hands the arm two identical inputs, so it
ties and the gate credits it 0.5: that is "did not read it", not "read it and
could not judge". It is every ``contradiction`` pair (an appended sentence; all
20 tied on the run above), and on long answers any variant whose edits all fall
in the tail (``wrong_numbers`` tied on 9 of 13; in review up to 37% of pairs on
the longest answers). ``padding`` inserts its filler between paragraphs from
the top, so it is never blind. The multilingual checkpoint defaults to 1024
tokens, so it truncates too unless ``--typed-max-len`` is set.
``report_fields()`` writes the budget, the checkpoint revision and the usage
(truncation count, seconds) into the saved report for this reason.

Entirely optional: nothing imports this module unless a typed arm is requested,
and the backend is an extra (`pip install 'dokimi[typed-scorer]'`).
"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

#: Answer dimensions and their ordered level descriptors. These mirror the four
#: dimensions the shipped aggregate weights, so a typed arm's number is on the
#: same scale as the judge's and the two can be compared directly.
TYPED_LEVELS: Dict[str, List[str]] = {
    "correctness": [
        "is wrong about this library",
        "is partly wrong",
        "is broadly right with errors in detail",
        "is correct throughout",
    ],
    "completeness": [
        "does not answer the question",
        "answers a small part of it",
        "answers most of it",
        "answers it fully",
    ],
    "code_quality": [
        "shows no usable commands or code",
        "shows code that would not run",
        "shows runnable code with rough edges",
        "shows correct, runnable code",
    ],
    "actionability": [
        "leaves the reader with nothing to do",
        "needs substantial work to act on",
        "is mostly actionable",
        "can be followed step by step",
    ],
}

#: Backends this module knows how to build. Keep the list short and explicit:
#: an arm whose numbers nobody has measured is not a baseline.
TYPED_BACKENDS = ("laya",)

DEFAULT_LAYA_REPO = "convaiinnovations/laya"


def typed_aggregate(scores: Dict[str, float]) -> float:
    """The judge's own aggregate — same weights, same rounding.

    Read from :class:`~dokimi.eval.judge.Judge` rather than restated,
    so a future reweighting of the judge moves this arm with it and the two stay
    on one scale, which is the property that makes the arm a baseline at all.
    """
    from dokimi.eval.judge import Judge

    return Judge._compute_aggregate(scores, Judge._STANDARD_WEIGHTS)


def _check_dimensions() -> None:
    """Fail at import if the typed levels and the judge's weights disagree.

    A dimension the judge weights but this module never asks about would score
    as 0 and drag every typed aggregate down without an error.
    """
    from dokimi.eval.judge import Judge

    weighted = set(Judge._STANDARD_WEIGHTS)
    if set(TYPED_LEVELS) != weighted:
        raise RuntimeError(
            f"typed_scorer.TYPED_LEVELS {sorted(TYPED_LEVELS)} does not match the "
            f"judge's weighted dimensions {sorted(weighted)}"
        )


_check_dimensions()


#: ``C:\\...`` or ``C:/...`` — a Windows drive path, never a Hub id.
_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")


def _is_local_path(target: str) -> bool:
    """A local checkpoint directory rather than a Hub ``owner/name`` id."""
    return (target.startswith(("/", ".", "~", "\\")) or bool(_DRIVE.match(target))
            or os.path.isdir(os.path.expanduser(target)))


def parse_spec(spec: str) -> Tuple[str, str, Optional[str]]:
    """``laya``, ``laya:<owner>/<name>[/<subfolder>]`` or ``laya:<local dir>``.

    Returns (backend, repo, subfolder). A Hub id has exactly two segments, so a
    third and later segments name a subfolder. A local directory (absolute,
    relative, ``~``, or any existing path) is passed through whole: splitting it
    the Hub way would load ``/localdisk`` with subfolder ``ckpt/laya``.
    """
    backend, _, rest = spec.partition(":")
    if backend not in TYPED_BACKENDS:
        raise ValueError(
            f"unknown typed scorer backend {backend!r}; known: {list(TYPED_BACKENDS)}"
        )
    target = rest.strip() or DEFAULT_LAYA_REPO
    if _is_local_path(target):
        path = os.path.expanduser(target)
        stripped = path.rstrip("/\\")
        return backend, stripped if stripped and not stripped.endswith(":") else path, None
    parts = target.strip("/").split("/")
    if any(not p for p in parts) or len(parts) < 2:
        raise ValueError(
            f"typed scorer target {target!r} is neither a Hub id (owner/name"
            f"[/subfolder]) nor a local directory"
        )
    repo = "/".join(parts[:2])
    subfolder = "/".join(parts[2:]) or None
    return backend, repo, subfolder


class TypedScorer:
    """Adapts a typed-decision model to the gate's `Scorer` protocol.

    Call signature is the gate's: ``(library, question, answer) -> float``.

    `usage` accumulates what the run actually did — including how many states
    were truncated and how many state tokens were dropped. The English
    checkpoint has a 512-token budget shared between the options and the state,
    and our answers are ~1500 tokens, so silent truncation is the normal case
    rather than an edge case; a number that was produced from a prefix of the
    answer should say so.
    """

    def __init__(
        self,
        spec: str = "laya",
        *,
        agent: Any = None,
        max_len: int = 0,
        threads: Optional[int] = None,
    ) -> None:
        self.backend, self.repo, self.subfolder = parse_spec(spec)
        self.max_len = max_len
        self.name = f"{self.backend}:{self.repo}" + (
            f"/{self.subfolder}" if self.subfolder else ""
        )
        self.usage: Dict[str, float] = {
            "calls": 0,
            "seconds": 0.0,
            "truncated": 0,
            "state_tokens_dropped": 0,
        }
        self._agent = agent if agent is not None else self._load(threads)

    def _load(self, threads: Optional[int]) -> Any:
        try:
            if threads:
                import torch

                torch.set_num_threads(threads)
            import laya
        except ImportError as exc:  # pragma: no cover - depends on the extra
            raise ImportError(
                "typed scorer backend 'laya' needs the optional dependency: "
                "pip install 'dokimi[typed-scorer]'"
            ) from exc
        kwargs = {"subfolder": self.subfolder} if self.subfolder else {}
        logger.info("Loading typed scorer %s", self.name)
        try:
            return laya.load(self.repo, **kwargs)
        except OSError as exc:  # unknown repo or subfolder, offline Hub
            raise OSError(f"cannot load typed scorer {self.name}: {exc}") from exc

    def _questions(self, library: str) -> Dict[str, Dict[str, Any]]:
        return {
            dim: {
                "type": "score",
                "instructions": (
                    f"Rate the ANSWER on {dim.replace('_', ' ')} for this "
                    f"{library} question."
                ),
                "criteria": list(levels),
            }
            for dim, levels in TYPED_LEVELS.items()
        }

    def __call__(self, library: str, question: str, answer: str) -> float:
        state = (
            f"LIBRARY: {library}\n\nQUESTION: {question}\n\nANSWER:\n{answer}"
        )
        kwargs = {"max_len": self.max_len} if self.max_len else {}
        started = time.time()
        result = self._agent.predict(state, self._questions(library), **kwargs)
        self.usage["seconds"] += time.time() - started
        self.usage["calls"] += 1
        usage = result.get("usage") or {}
        self.usage["truncated"] += bool(usage.get("truncated"))
        self.usage["state_tokens_dropped"] += int(
            usage.get("state_tokens_dropped") or 0
        )
        scores = {
            dim: 100.0 * float(result["answers"][dim]["score"]) / (len(levels) - 1)
            for dim, levels in TYPED_LEVELS.items()
        }
        return typed_aggregate(scores)

    @property
    def effective_max_len(self) -> Optional[int]:
        """The token budget the checkpoint actually used: ``--typed-max-len``, or its own."""
        if self.max_len:
            return self.max_len
        cfg = getattr(self._agent, "cfg", None)
        value = cfg.get("max_len") if isinstance(cfg, dict) else None
        return int(value) if value is not None else None

    def report_fields(self) -> Dict[str, Any]:
        """What a saved report needs to tell two typed runs apart.

        Without these, a 512-token and a 2048-token run of one checkpoint wrote
        the same label (0.527 against 0.477 on the same pairs in review), and
        nothing in the file said how much of each answer the arm had read.
        """
        return {
            "scorer": self.name,
            "revision": getattr(self._agent, "revision", None),
            "max_len": self.effective_max_len,
            "usage": {k: (round(v, 3) if isinstance(v, float) else v) for k, v in self.usage.items()},
        }

    def usage_summary(self) -> str:
        calls = max(1, int(self.usage["calls"]))
        return (
            f"{int(self.usage['calls'])} scores, {self.usage['seconds']:.0f}s, "
            f"{self.usage['seconds'] / calls:.3f}s/score, truncated states "
            f"{int(self.usage['truncated'])}/{int(self.usage['calls'])}, "
            f"mean state tokens dropped "
            f"{self.usage['state_tokens_dropped'] / calls:.0f}"
        )


def typed_scorer(
    spec: str = "laya",
    *,
    agent: Any = None,
    max_len: int = 0,
    threads: Optional[int] = None,
) -> TypedScorer:
    """Build a typed baseline arm. Mirrors `judge_validity.judge_scorer`."""
    return TypedScorer(spec, agent=agent, max_len=max_len, threads=threads)
