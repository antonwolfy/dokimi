"""Multi-evaluator (LLM Judge Panel) for doc-benchmark.

Design principles:
- Roles are differentiated in BOTH criteria perspective AND weighted aggregate
- LLM outputs only 5 raw scores; Python computes weighted aggregate (reliable)
- reasoning comes FIRST in JSON (chain-of-thought anchors the scores)
- code_quality = 100 when no code present (avoids penalizing text-only answers)
- JSON extracted via regex (robust against leading text from LLM)
- Prompts use __PLACEHOLDER__ substitution (safe from .format() conflicts)
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from doc_benchmarks.llm import llm_call

logger = logging.getLogger(__name__)

# ── Score fields & weights ────────────────────────────────────────────────────

SCORE_FIELDS = ("correctness", "completeness", "specificity", "code_quality", "actionability")

# Weights per role — Python computes aggregate, not LLM
ROLE_WEIGHTS: Dict[str, Dict[str, float]] = {
    "technical_expert":   {"correctness": 2.0, "completeness": 1.0, "specificity": 1.5, "code_quality": 1.0, "actionability": 1.0},
    "developer_advocate": {"correctness": 1.0, "completeness": 1.0, "specificity": 1.0, "code_quality": 1.5, "actionability": 2.0},
    "doc_reviewer":       {"correctness": 1.0, "completeness": 2.0, "specificity": 1.5, "code_quality": 1.0, "actionability": 1.0},
}

# ── Calibration anchors (shared) ──────────────────────────────────────────────

_ANCHORS = """
Score anchors — interpolate between these points:
  100 = perfect: complete, accurate, specific, immediately usable
   90 = excellent: tiny wording issues or one minor omission, no impact on usability
   80 = good: correct and useful, one noticeable gap or slight imprecision
   70 = acceptable: core answer is right, but missing some context or steps
   60 = partial: answers part of the question well, ignores another part
   50 = mediocre: significant gaps, or correct but too vague to act on
   40 = weak: some useful info but notable inaccuracies or missing key details
   30 = poor: mostly off-target or incorrect, one or two correct points
   20 = very poor: nearly all wrong or irrelevant, misleads the user
   10 = almost useless: one marginally correct detail in an otherwise wrong answer
    0 = completely wrong, irrelevant, or harmful to follow
"""

# ── Judge role prompts ────────────────────────────────────────────────────────

_ROLE_INTROS: Dict[str, str] = {
    "technical_expert": (
        "You are a STRICT TECHNICAL EXPERT evaluating a documentation answer.\n"
        "PRIMARY CONCERN: FACTUAL ACCURACY and TECHNICAL DEPTH.\n"
        "- Penalize vague, hand-wavy, or technically incorrect details heavily.\n"
        "- A wrong answer scores ≤ 40 on correctness even if well-written.\n"
        "- Judge 'specificity' harshly: generic advice not tied to __LIBRARY__ scores ≤ 30.\n"
        "- For 'completeness': does it address ALL parts of the question?\n"
        "- For 'actionability': as a technical expert, would YOU use this answer?"
    ),
    "developer_advocate": (
        "You are a DEVELOPER ADVOCATE evaluating a documentation answer.\n"
        "PRIMARY CONCERN: PRACTICAL USEFULNESS — would a developer be unblocked right now?\n"
        "- A theoretically correct but hard-to-apply answer scores ≤ 40 on actionability.\n"
        "- Prioritize working code examples and clear step-by-step instructions.\n"
        "- For 'correctness': acceptable if minor inaccuracies don't affect usability.\n"
        "- For 'completeness': enough to get started? Partial answers can score 70+ if actionable."
    ),
    "doc_reviewer": (
        "You are a DOCUMENTATION QUALITY REVIEWER evaluating a documentation answer.\n"
        "PRIMARY CONCERN: COMPLETENESS and FIDELITY TO THE PROVIDED CONTEXT.\n"
        "- An answer ignoring key aspects of the question scores ≤ 40 on completeness.\n"
        "- Check: does the answer stay within the scope of the provided documentation context?\n"
        "- Penalize answers that introduce information NOT present in the context.\n"
        "- For 'specificity': does it reference __LIBRARY__-specific APIs, not generic patterns?"
    ),
}

_PROMPT_TEMPLATE = """\
__ROLE_INTRO__

Library: __LIBRARY__
Question: __QUESTION__
Answer: __ANSWER__
Documentation context: __CONTEXT__

Rate each dimension 0–100. Use these calibration anchors:
__ANCHORS__

Dimensions to rate:
1. correctness   — Is the answer factually accurate for __LIBRARY__?
2. completeness  — Does it address ALL parts of the question?
3. specificity   — Is it specific to __LIBRARY__ (not generic)?
4. code_quality  — Is the code correct, runnable, idiomatic __LIBRARY__ code?
                   IF NO CODE IN THE ANSWER: set code_quality = 100 (not applicable).
5. actionability — Can the user directly apply this to their problem right now?

IMPORTANT: Output ONLY a JSON object. Do NOT wrap in markdown. Do NOT add any text before or after.
Put "reasoning" FIRST (it helps you think before scoring):
{"reasoning": "one sentence: main strength or weakness", "correctness": N, "completeness": N, "specificity": N, "code_quality": N, "actionability": N}
"""

JUDGE_ROLES: Dict[str, str] = {
    role: _PROMPT_TEMPLATE
    .replace("__ROLE_INTRO__", intro)
    .replace("__ANCHORS__", _ANCHORS)
    for role, intro in _ROLE_INTROS.items()
}

DEFAULT_PANEL = ["technical_expert", "developer_advocate", "doc_reviewer"]

# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class JudgeVote:
    role: str
    model: str
    provider: str
    scores: Dict[str, float]    # raw scores only (no aggregate — computed by Python)
    reasoning: str
    aggregate: Optional[float] = None   # Python-computed weighted aggregate
    error: Optional[str] = None


@dataclass
class PanelVerdict:
    votes: List[JudgeVote]
    mean_aggregate: Optional[float]
    std_aggregate: Optional[float]
    agreement_score: Optional[float]   # 0–1; 1.0 = perfect agreement
    mean_dimensions: Dict[str, float] = field(default_factory=dict)

    @property
    def valid_votes(self) -> List[JudgeVote]:
        return [v for v in self.votes if v.aggregate is not None]

    @property
    def disagreement_flag(self) -> bool:
        return self.std_aggregate is not None and self.std_aggregate > 15.0


@dataclass
class JudgeConfig:
    role: str
    model: str
    provider: str


# ── Panel ─────────────────────────────────────────────────────────────────────

class JudgePanel:
    """Run multiple LLM judges in parallel and aggregate their verdicts."""

    def __init__(
        self,
        judges: Optional[List[JudgeConfig]] = None,
        default_model: str = "gpt-4o-mini",
        default_provider: str = "openai",
        concurrency: int = 6,
    ):
        self.judges = judges or [
            JudgeConfig(role=role, model=default_model, provider=default_provider)
            for role in DEFAULT_PANEL
        ]
        self.concurrency = concurrency

    def _build_prompt(self, role: str, question: str, answer: str,
                      library_name: str, context: str) -> str:
        template = JUDGE_ROLES.get(role, JUDGE_ROLES["technical_expert"])
        # Use sequential replace with unique sentinels to avoid injection
        # (each placeholder is distinct so no cross-substitution is possible)
        return (
            template
            .replace("__LIBRARY__", library_name)
            .replace("__QUESTION__", question)
            .replace("__ANSWER__", answer)
            .replace("__CONTEXT__", context or "(No documentation provided)")
        )

    @staticmethod
    def _compute_aggregate(role: str, scores: Dict[str, float]) -> float:
        """Compute weighted aggregate in Python — never trust LLM to do math."""
        weights = ROLE_WEIGHTS.get(role, {k: 1.0 for k in SCORE_FIELDS})
        total_weight = sum(weights.values())
        weighted_sum = sum(scores.get(k, 0.0) * weights.get(k, 1.0) for k in SCORE_FIELDS)
        return round(weighted_sum / total_weight, 1)

    @staticmethod
    def _extract_json(text: str) -> Dict:
        """Robust JSON extraction — handles leading text and markdown fences."""
        # Try direct parse first
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass
        # Extract from markdown fence
        fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if fence:
            try:
                return json.loads(fence.group(1).strip())
            except json.JSONDecodeError:
                pass
        # Find first { ... } block
        brace = re.search(r"\{[\s\S]*\}", text)
        if brace:
            return json.loads(brace.group(0))
        raise ValueError(f"No JSON found in LLM response: {text[:200]!r}")

    def _call_judge(self, config: JudgeConfig, question: str, answer: str,
                    library_name: str, context: str) -> JudgeVote:
        prompt = self._build_prompt(config.role, question, answer, library_name, context)
        try:
            raw = llm_call(prompt, model=config.model, provider=config.provider)
            data = self._extract_json(raw)
            scores: Dict[str, float] = {}
            for k in SCORE_FIELDS:
                if k in data:
                    scores[k] = max(0.0, min(100.0, float(data[k])))
            # Python computes aggregate (ignores any aggregate LLM might have returned)
            agg = self._compute_aggregate(config.role, scores) if scores else None
            return JudgeVote(
                role=config.role, model=config.model, provider=config.provider,
                scores=scores, reasoning=str(data.get("reasoning", "")), aggregate=agg,
            )
        except Exception as exc:
            logger.warning(f"Judge '{config.role}' ({config.model}) failed: {exc}")
            return JudgeVote(
                role=config.role, model=config.model, provider=config.provider,
                scores={}, reasoning="", error=str(exc),
            )

    def evaluate(self, question: str, answer: str, library_name: str,
                 context: str = "") -> PanelVerdict:
        votes: List[JudgeVote] = []
        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            futures = {
                pool.submit(self._call_judge, cfg, question, answer, library_name, context): cfg
                for cfg in self.judges
            }
            for future in as_completed(futures):
                votes.append(future.result())
        return self._aggregate(votes)

    def _aggregate(self, votes: List[JudgeVote]) -> PanelVerdict:
        valid = [v for v in votes if v.aggregate is not None]
        if not valid:
            return PanelVerdict(votes=votes, mean_aggregate=None,
                                std_aggregate=None, agreement_score=None)
        aggs = [v.aggregate for v in valid]
        mean_agg = round(statistics.mean(aggs), 1)
        std_agg = round(statistics.stdev(aggs), 1) if len(aggs) > 1 else 0.0
        agreement = round(max(0.0, 1.0 - std_agg / 50.0), 3)
        mean_dims: Dict[str, float] = {}
        for dim in SCORE_FIELDS:
            vals = [v.scores[dim] for v in valid if dim in v.scores]
            if vals:
                mean_dims[dim] = round(statistics.mean(vals), 1)
        return PanelVerdict(votes=votes, mean_aggregate=mean_agg,
                            std_aggregate=std_agg, agreement_score=agreement,
                            mean_dimensions=mean_dims)

    def _score_answer_entry(self, ans_data: Optional[Dict], question: str,
                            library_name: str) -> Optional[PanelVerdict]:
        if not ans_data or not ans_data.get("answer"):
            return None
        ctx = "\n".join(d.get("content", "") for d in ans_data.get("retrieved_docs", []))
        return self.evaluate(question, ans_data["answer"], library_name, ctx)

    def evaluate_answers(self, answers: List[Dict[str, Any]], library_name: str,
                         output_path: Optional[Path] = None,
                         limit: Optional[int] = None) -> List[Dict[str, Any]]:
        if limit:
            answers = answers[:limit]
        results = []
        n = len(answers)
        for i, answer in enumerate(answers, 1):
            q_id = answer.get("question_id", f"q{i}")
            question = answer.get("question", "")
            print(f"[{i}/{n}] Panel: {q_id}…", flush=True)
            with_v = self._score_answer_entry(answer.get("with_docs"), question, library_name)
            without_v = self._score_answer_entry(answer.get("without_docs"), question, library_name)
            delta = None
            if (with_v and with_v.mean_aggregate is not None
                    and without_v and without_v.mean_aggregate is not None):
                delta = round(with_v.mean_aggregate - without_v.mean_aggregate, 1)
            results.append({
                "question_id": q_id,
                "question": question,
                "panel_size": len(self.judges),
                "with_docs": _verdict_to_dict(with_v),
                "without_docs": _verdict_to_dict(without_v),
                "delta": delta,
            })
            if output_path:
                _save_incremental(results, output_path, library_name, self)
        return results


# ── Helpers ───────────────────────────────────────────────────────────────────

def _verdict_to_dict(v: Optional[PanelVerdict]) -> Optional[Dict[str, Any]]:
    if v is None:
        return None
    return {
        "aggregate": v.mean_aggregate,
        "std": v.std_aggregate,
        "agreement_score": v.agreement_score,
        "disagreement_flag": v.disagreement_flag,
        "dimensions": v.mean_dimensions,
        "votes": [
            {"role": vt.role, "model": vt.model, "aggregate": vt.aggregate,
             "scores": vt.scores, "reasoning": vt.reasoning, "error": vt.error}
            for vt in v.votes
        ],
    }


def _save_incremental(results: List[Dict], path: Path, library_name: str,
                      panel: JudgePanel) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    output = {
        "evaluated_at": _timestamp(),
        "judge_model": f"panel({len(panel.judges)})",
        "panel_config": {
            "size": len(panel.judges),
            "roles": [j.role for j in panel.judges],
            "models": [f"{j.provider}/{j.model}" for j in panel.judges],
        },
        "library_name": library_name,
        "total_evaluations": len(results),
        "evaluations": results,
    }
    with open(tmp, "w") as f:
        json.dump(output, f, indent=2)
    os.replace(tmp, path)


def _timestamp() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
