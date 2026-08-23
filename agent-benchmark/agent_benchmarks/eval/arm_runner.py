"""Run an N-arm treatment comparison: generate (and optionally judge) answers.

Generalizes the binary ``with_docs``/``without_docs`` answerer to an arbitrary
set of :class:`~agent_benchmarks.treatments.base.Treatment` arms — documentation
injection, MCP-served docs, agent persona prompts, and skills — scored by the
same LLM-as-judge used elsewhere.
"""

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent_benchmarks.llm import llm_call_with_usage
from agent_benchmarks.eval import stats as arm_stats
from agent_benchmarks.eval.arm_summary import cost_summary, summarize_agentic_usage
from agent_benchmarks.eval.cells import Cell
from agent_benchmarks.metrics.usage import to_record
from agent_benchmarks.treatments.base import Treatment

logger = logging.getLogger(__name__)

ANSWER_PROMPT_WITH_CONTEXT = """You are answering a user question.

**Question:** {question}

**Relevant context:**
{context}

**Task:**
Answer the question using the provided context above where relevant. Be specific, accurate, and actionable. Include code examples if relevant.

**Answer:**"""

ANSWER_PROMPT_PLAIN = """Answer the following user question. Be specific and include code examples if relevant.

**Question:** {question}

**Answer:**"""

MAX_CONTEXT_CHARS = 15_000

# Curated golden sets carry verified answer statements in ``expected_topics``,
# which are usable as judge ground truth. Auto-generated sets put short keyword
# labels in the same field (measured: ~14-19 chars/topic, versus 78-207 for the
# golden sets), and grading a full answer against bare keywords would penalise
# correct answers. Only promote topics that are prose-length.
MIN_GROUND_TRUTH_TOPIC_CHARS = 40


def _ground_truth_from_topics(q: Dict[str, Any]) -> Optional[str]:
    """Build judge ground truth from ``expected_topics``, when they are substantive.

    Returns ``None`` for keyword-style topics so that such questions keep using
    the ungrounded rubric rather than being scored against a word list.
    """
    topics = q.get("expected_topics") or []
    if not isinstance(topics, list):
        return None
    statements = [str(t).strip() for t in topics if str(t).strip()]
    if not statements:
        return None
    mean_len = sum(len(s) for s in statements) / len(statements)
    if mean_len < MIN_GROUND_TRUTH_TOPIC_CHARS:
        return None
    return "\n".join(f"- {s}" for s in statements)


class ArmRunner:
    """Generate answers for each treatment arm and (optionally) judge them."""

    # Pure rollups over the answer records, kept in eval/arm_summary.py so this
    # module stays under the repo's 500-line ceiling. Re-attached here so
    # `self._cost_summary(...)` and existing tests keep working unchanged.
    _summarize_agentic_usage = staticmethod(summarize_agentic_usage)
    _cost_summary = staticmethod(cost_summary)

    def __init__(
        self,
        treatments: List[Treatment],
        model: str = "gpt-4o-mini",
        provider: str = "openai",
        api_key: Optional[str] = None,
        max_iterations: int = 6,
        harness: str = "arms-runner",
        plugin_set: Optional[Dict[str, Any]] = None,
        matrix_cell: Optional[str] = None,
        max_tokens: Optional[int] = None,
        grounded_from_topics: bool = False,
        stats_correction: str = "holm",
    ):
        if not treatments:
            raise ValueError("ArmRunner requires at least one treatment arm")
        # Rejected here rather than at summarize time: the correction is only
        # applied after every arm has been answered and judged, so a typo would
        # otherwise surface after the whole run has been paid for.
        if stats_correction not in arm_stats.CORRECTIONS:
            raise ValueError(
                f"stats_correction must be one of {arm_stats.CORRECTIONS}, "
                f"got {stats_correction!r}"
            )
        self.treatments = treatments
        self.stats_correction = stats_correction
        self.model = model
        self.provider = provider
        self.api_key = api_key
        self.max_iterations = max_iterations
        self.max_tokens = max_tokens
        self.grounded_from_topics = grounded_from_topics
        self.harness = harness
        self.matrix_cell = matrix_cell
        self.plugin_set = plugin_set or {
            "plugin_set": "none",
            "plugin_set_id": "sha256:e3b0c44298fc1c149afbf4c8996fb924",
            "plugins": [],
        }

    @property
    def arm_names(self) -> List[str]:
        return [t.name for t in self.treatments]

    def _run_config(self) -> Dict[str, Any]:
        """Request-shaping settings, recorded so a run stays interpretable later.

        Two runs of the same questions under the same model are not comparable if
        they used different budgets: ``max_tokens`` decides whether an answer was
        truncated, and ``max_iterations`` decides whether an agentic arm ran out
        of tool-call rounds before answering. Without these, a truncated run and a
        complete one are indistinguishable in the artifact.
        """
        return {
            "max_tokens": self.max_tokens,
            "max_iterations": self.max_iterations,
            "grounded_from_topics": self.grounded_from_topics,
        }

    def run(
        self,
        library_name: str,
        questions: List[Dict[str, Any]],
        library_id: Optional[str] = None,
        concurrency: int = 5,
    ) -> List[Dict[str, Any]]:
        """Answer every question under every arm. Returns one record per question."""
        n = len(questions)
        results: Dict[int, Dict[str, Any]] = {}
        lock = threading.Lock()
        done = [0]

        def _process(idx: int, q: Dict[str, Any]) -> None:
            rec = self._answer_question(library_name, library_id, q)
            with lock:
                results[idx] = rec
                done[0] += 1
                print(f"[{done[0]}/{n}] {rec['question_id']} OK", flush=True)

        print(f"Running {len(self.treatments)} arms over {n} questions "
              f"(arms: {', '.join(self.arm_names)})", flush=True)
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = [pool.submit(_process, i, q) for i, q in enumerate(questions)]
            for f in as_completed(futures):
                f.result()

        return [results[i] for i in range(n)]

    def _answer_question(
        self, library_name: str, library_id: Optional[str], q: Dict[str, Any]
    ) -> Dict[str, Any]:
        question_text = q.get("question") or q.get("text") or q.get("question_text", "")
        qid = q.get("id") or q.get("question_id") or "unknown_q"

        arms: Dict[str, Any] = {}
        for treatment in self.treatments:
            arms[treatment.name] = self._answer_one_arm(
                treatment, question_text, library_name, library_id
            )

        rec = {
            "question_id": qid,
            "question_text": question_text,
            "library_name": library_name,
            "category": q.get("category"),
            "difficulty": q.get("difficulty"),
            "persona": q.get("persona"),
            "arms": arms,
        }
        ground_truth = q.get("ground_truth_chunk")
        if not ground_truth and self.grounded_from_topics:
            ground_truth = _ground_truth_from_topics(q)
        if ground_truth:
            rec["ground_truth_chunk"] = ground_truth
        return rec

    def _answer_one_arm(
        self,
        treatment: Treatment,
        question_text: str,
        library_name: str,
        library_id: Optional[str],
    ) -> Dict[str, Any]:
        t0 = time.time()
        try:
            cfg = treatment.prepare(question_text, library_name, library_id)
        except Exception as exc:
            logger.exception("Arm %s prepare() failed", treatment.name)
            return {"error": f"prepare_failed: {exc}", "answer": None}

        from agent_benchmarks.plugins import take_output_shapers
        shapers, cfg_metadata = take_output_shapers(cfg)

        if cfg.is_agentic:
            return self._answer_agentic_arm(cfg, question_text, t0, shapers, cfg_metadata)

        if cfg.has_context:
            context = "\n\n---\n\n".join(c["content"] for c in cfg.injected_context)
            prompt = ANSWER_PROMPT_WITH_CONTEXT.format(
                question=question_text, context=context[:MAX_CONTEXT_CHARS]
            )
        else:
            prompt = ANSWER_PROMPT_PLAIN.format(question=question_text)

        try:
            answer_text, usage = llm_call_with_usage(
                prompt=prompt,
                model=self.model,
                provider=self.provider,
                api_key=self.api_key,
                system=cfg.system_prompt,
                max_tokens=self.max_tokens,
            )
        except Exception as exc:
            logger.exception("Arm %s answer generation failed", treatment.name)
            return {"error": f"generation_failed: {exc}", "answer": None,
                    "metadata": cfg_metadata}

        raw_chars = len(answer_text or "")
        final_text = self._apply_shapers(shapers, answer_text)
        final_chars = len(final_text or "")

        rec = to_record(usage, self.model, self.provider)
        return {
            "answer": final_text,
            "raw_answer": answer_text if shapers else None,
            "model": self.model,
            "harness": self.harness,
            "plugin_set": self.plugin_set["plugin_set"],
            "plugin_set_id": self.plugin_set["plugin_set_id"],
            "used_system_prompt": bool(cfg.system_prompt),
            "context_chunks": [
                {
                    "source": c.get("source", "unknown"),
                    "snippet": (c["content"][:200] + "…") if len(c["content"]) > 200 else c["content"],
                    "relevance_score": c.get("relevance_score"),
                }
                for c in cfg.injected_context
            ],
            "token_usage": rec.as_token_usage_dict(),
            "metrics": rec.as_metrics_dict(answer_chars=raw_chars, final_chars=final_chars),
            "metadata": cfg_metadata,
            "elapsed_sec": round(time.time() - t0, 2),
        }

    @staticmethod
    def _apply_shapers(shapers, answer_text):
        """Run output shapers over a raw answer (no-op when there are none)."""
        if not shapers:
            return answer_text
        from agent_benchmarks.plugins import apply_output_shapers
        return apply_output_shapers(shapers, answer_text or "")

    def _answer_agentic_arm(
        self, cfg, question_text: str, t0: float, shapers=None, cfg_metadata=None
    ) -> Dict[str, Any]:
        """Run an arm whose treatment offers tools via the agent loop."""
        from agent_benchmarks.eval.agent_runner import run_agent_loop

        shapers = shapers or []
        cfg_metadata = cfg_metadata if cfg_metadata is not None else cfg.metadata

        try:
            result = run_agent_loop(
                question=question_text,
                tools=cfg.tools,
                model=self.model,
                provider=self.provider,
                system_prompt=cfg.system_prompt,
                api_key=self.api_key,
                max_iterations=self.max_iterations,
                max_tokens=self.max_tokens,
            )
        except Exception as exc:
            logger.exception("Agentic arm failed")
            return {"error": f"agent_failed: {exc}", "answer": None,
                    "metadata": cfg_metadata}

        raw_answer = result["answer"]
        final_answer = self._apply_shapers(shapers, raw_answer)
        rec = to_record(result.get("usage") or result["token_usage"], self.model, self.provider)
        metrics = rec.as_metrics_dict(
            answer_chars=len(raw_answer or ""), final_chars=len(final_answer or "")
        )
        per_turn = result.get("per_turn")
        if per_turn is not None:
            metrics["per_turn"] = per_turn
        return {
            "answer": final_answer,
            "raw_answer": raw_answer if shapers else None,
            "model": self.model,
            "harness": self.harness,
            "plugin_set": self.plugin_set["plugin_set"],
            "plugin_set_id": self.plugin_set["plugin_set_id"],
            "agentic": True,
            "used_system_prompt": bool(cfg.system_prompt),
            "context_chunks": [],
            "transcript": result["transcript"],
            "tool_call_count": result["tool_call_count"],
            "tool_usage": result.get("tool_usage", {}),
            "discoverability": result.get("tool_usage", {}).get("skill", {}),
            "iterations": result["iterations"],
            "stopped_reason": result["stopped_reason"],
            "token_usage": rec.as_token_usage_dict(),
            "metrics": metrics,
            "metadata": cfg_metadata,
            "elapsed_sec": round(time.time() - t0, 2),
        }

    # ── Judging ─────────────────────────────────────────────────────────
    def judge(
        self,
        judge,
        library_name: str,
        records: List[Dict[str, Any]],
        baseline_arm: str = "baseline",
        concurrency: int = 5,
    ) -> List[Dict[str, Any]]:
        """Score each arm's answer with the given Judge; add per-arm deltas.

        Deltas are computed against *baseline_arm* when that arm is present.
        """
        def _score(rec: Dict[str, Any]) -> Dict[str, Any]:
            scores: Dict[str, Any] = {}
            gt = rec.get("ground_truth_chunk")
            for arm_name, arm in rec.get("arms", {}).items():
                if not arm or not arm.get("answer"):
                    scores[arm_name] = None
                    continue
                context = "\n".join(
                    c.get("snippet", "") for c in arm.get("context_chunks", [])
                ) or "(No documentation retrieved)"
                try:
                    scores[arm_name] = judge.score_answer(
                        library_name=library_name,
                        question=rec["question_text"],
                        answer=arm["answer"],
                        context=context,
                        ground_truth=gt,
                    )
                except Exception as exc:
                    logger.exception("Judging arm %s failed", arm_name)
                    scores[arm_name] = {"error": str(exc)}

            deltas = {}
            base = scores.get(baseline_arm)
            base_agg = base.get("aggregate") if isinstance(base, dict) else None
            if base_agg is not None:
                for arm_name, s in scores.items():
                    if arm_name != baseline_arm and isinstance(s, dict) and "aggregate" in s:
                        deltas[arm_name] = round(s["aggregate"] - base_agg, 1)

            return {
                "question_id": rec["question_id"],
                "question_text": rec["question_text"],
                "category": rec.get("category"),
                "difficulty": rec.get("difficulty"),
                "scores": scores,
                "deltas_vs_baseline": deltas,
            }

        n = len(records)
        out: Dict[int, Dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {pool.submit(_score, r): i for i, r in enumerate(records)}
            for f in as_completed(futures):
                idx = futures[f]
                out[idx] = f.result()
        return [out[i] for i in range(n)]

    def build_output(
        self,
        library_name: str,
        records: List[Dict[str, Any]],
        evaluations: Optional[List[Dict[str, Any]]] = None,
        baseline_arm: str = "baseline",
        judge: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Assemble the serialisable arms-comparison artifact."""
        out: Dict[str, Any] = {
            "schema_version": "arms.v1",
            "generated_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z",
            "library_name": library_name,
            "model": self.model,
            "provider": self.provider,
            "harness": self.harness,
            "plugin_set": self.plugin_set["plugin_set"],
            "plugin_set_id": self.plugin_set["plugin_set_id"],
            "plugins": self.plugin_set["plugins"],
            "cell": Cell(self.model, self.harness, self.plugin_set["plugin_set"]).key,
            "arms": self.arm_names,
            "baseline_arm": baseline_arm,
            "total_questions": len(records),
            "run_config": self._run_config(),
            "grounded_from_topics": self.grounded_from_topics,
            "grounded_questions": sum(
                1 for r in records if r.get("ground_truth_chunk")
            ),
            "answers": records,
            "cost_summary": self._cost_summary(records),
            "agentic_usage_summary": self._summarize_agentic_usage(records),
        }
        if self.matrix_cell:
            out["matrix_cell"] = self.matrix_cell
        if evaluations is not None:
            out["evaluations"] = evaluations
            out["summary"] = self._summarize(evaluations, baseline_arm)
            if judge is not None:
                out["judge_model"] = getattr(judge, "model", None)
                out["judge_provider"] = getattr(judge, "provider", None)
        # Judge-side token/cost telemetry, when a judge ran (mirrors the answer
        # cost_summary so a full run's spend is auditable from one artifact).
        if judge is not None and hasattr(judge, "_usage_totals"):
            with judge._usage_lock:
                totals = dict(judge._usage_totals)
            totals["cost_usd"] = (
                round(totals["cost_usd"], 6) if totals["cost_known_calls"] else None
            )
            out["judge_metrics"] = totals
        return out

    def _summarize(
        self, evaluations: List[Dict[str, Any]], baseline_arm: str
    ) -> Dict[str, Any]:
        per_arm: Dict[str, List[float]] = {name: [] for name in self.arm_names}
        for ev in evaluations:
            for arm_name, s in ev.get("scores", {}).items():
                if isinstance(s, dict) and isinstance(s.get("aggregate"), (int, float)):
                    per_arm.setdefault(arm_name, []).append(float(s["aggregate"]))

        summary: Dict[str, Any] = {"per_arm": {}}
        base_avg = None
        for arm_name, vals in per_arm.items():
            avg = round(sum(vals) / len(vals), 1) if vals else None
            summary["per_arm"][arm_name] = {"avg_aggregate": avg, "n": len(vals)}
            if arm_name == baseline_arm:
                base_avg = avg
        if base_avg is not None:
            for arm_name, stats in summary["per_arm"].items():
                avg = stats["avg_aggregate"]
                stats["delta_vs_baseline"] = (
                    round(avg - base_avg, 1) if avg is not None and arm_name != baseline_arm else None
                )

        # Paired statistics. Every arm is tested against the *same* baseline
        # sample question-by-question, so the arms are mutually comparable and
        # p-values get corrected across the family. Unpaired means above are
        # kept as-is for artifact compatibility.
        arm_names = list(summary["per_arm"].keys())
        significance = arm_stats.arm_significance(
            evaluations, baseline_arm, arm_names, correction=self.stats_correction
        )
        for arm_name, sig in significance.items():
            summary["per_arm"].setdefault(arm_name, {})["significance"] = sig

        # Interaction contrasts are their own hypothesis family, corrected
        # among themselves rather than pooled with the arm comparisons above.
        interactions = arm_stats.interaction_significance(
            evaluations, arm_names, baseline_arm, correction=self.stats_correction
        )
        if interactions:
            summary["interactions"] = interactions

        return summary

    @staticmethod
    def save(output: Dict[str, Any], path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(output, indent=2), encoding="utf-8")
        logger.info("Saved arms comparison to %s", path)
