"""Per-arm rollups over answer records: agentic tool use, cost, and latency.

Split out of :mod:`agent_benchmarks.eval.arm_runner` to keep that module under
the repo's 500-line ceiling. Both functions are pure aggregations over the
records ``ArmRunner.run`` produced, and are re-attached to ``ArmRunner`` as
``_summarize_agentic_usage`` / ``_cost_summary`` so existing call sites and
tests keep working.
"""

from __future__ import annotations

from typing import Any, Dict, List


def summarize_agentic_usage(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate tool-use/discoverability signals from answer records."""
    stats: Dict[str, Dict[str, Any]] = {}
    for rec in records:
        for arm_name, arm in rec.get("arms", {}).items():
            if not isinstance(arm, dict) or not arm.get("agentic"):
                continue
            s = stats.setdefault(
                arm_name,
                {
                    "n": 0,
                    "tool_call_total": 0,
                    "tool_used_n": 0,
                    "iteration_total": 0,
                    "skill_offered_n": 0,
                    "skill_called_n": 0,
                    "skill_call_total": 0,
                },
            )
            s["n"] += 1
            tool_calls = int(arm.get("tool_call_count") or 0)
            s["tool_call_total"] += tool_calls
            if tool_calls > 0:
                s["tool_used_n"] += 1
            s["iteration_total"] += int(arm.get("iterations") or 0)

            skill = (arm.get("tool_usage") or {}).get("skill") or {}
            if skill.get("offered"):
                s["skill_offered_n"] += 1
            if skill.get("called"):
                s["skill_called_n"] += 1
            s["skill_call_total"] += int(skill.get("call_count") or 0)

    summary: Dict[str, Any] = {}
    for arm_name, s in stats.items():
        n = s["n"] or 1
        skill_offered_n = s["skill_offered_n"] or 0
        summary[arm_name] = {
            "n": s["n"],
            "avg_tool_calls": round(s["tool_call_total"] / n, 2),
            "tool_use_rate": round(s["tool_used_n"] / n, 3),
            "avg_iterations": round(s["iteration_total"] / n, 2),
            "skill_offered_n": skill_offered_n,
            "skill_called_n": s["skill_called_n"],
            "skill_load_rate": (
                round(s["skill_called_n"] / skill_offered_n, 3)
                if skill_offered_n else None
            ),
            "avg_skill_calls": (
                round(s["skill_call_total"] / skill_offered_n, 2)
                if skill_offered_n else None
            ),
        }
    return summary

def cost_summary(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Per-arm rollup of cost, tokens, latency, TTFT, and cache-hit ratio.

    Aggregates the per-row ``metrics{}`` blocks. ``cost_usd`` is summed only
    over priced rows (``None`` rows are skipped); the cache-hit ratio guards
    against a zero prompt-token denominator. The exact ratio is provider-
    dependent — here it is read cache tokens / prompt tokens.
    """
    per_arm: Dict[str, Dict[str, Any]] = {}
    for rec in records:
        for arm_name, arm in rec.get("arms", {}).items():
            if not isinstance(arm, dict):
                continue
            m = arm.get("metrics")
            if not isinstance(m, dict):
                continue
            acc = per_arm.setdefault(arm_name, {
                "n": 0, "total_llm_calls": 0,
                "cost_usd": 0.0, "cost_known_n": 0,
                "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
                "cache_read_tokens": 0, "latency_sec": 0.0,
                "ttft_sec_sum": 0.0, "ttft_n": 0,
            })
            acc["n"] += 1
            n_calls = m.get("n_calls", 1)
            acc["total_llm_calls"] += n_calls
            if m.get("cost_usd") is not None:
                acc["cost_usd"] += m["cost_usd"]
                acc["cost_known_n"] += m.get("cost_known_calls", n_calls) or 0
            for k in ("prompt_tokens", "completion_tokens", "total_tokens",
                      "cache_read_tokens"):
                acc[k] += m.get(k, 0) or 0
            acc["latency_sec"] += m.get("latency_sec", 0.0) or 0.0
            if m.get("ttft_sec") is not None:
                acc["ttft_sec_sum"] += m["ttft_sec"]
                acc["ttft_n"] += 1

    out: Dict[str, Any] = {}
    for arm_name, acc in per_arm.items():
        n = acc["n"] or 1
        prompt = acc["prompt_tokens"]
        out[arm_name] = {
            "n": acc["n"],
            "total_cost_usd": (round(acc["cost_usd"], 6)
                               if acc["cost_known_n"] else None),
            # How many rows the cost total covers — when < n, the dollar
            # figure is a partial sum (some LLM calls had no litellm pricing).
            "cost_known_n": acc["cost_known_n"],
            "total_llm_calls": acc["total_llm_calls"],
            "prompt_tokens": acc["prompt_tokens"],
            "completion_tokens": acc["completion_tokens"],
            "total_tokens": acc["total_tokens"],
            "mean_latency_sec": round(acc["latency_sec"] / n, 4),
            "mean_ttft_sec": (round(acc["ttft_sec_sum"] / acc["ttft_n"], 4)
                              if acc["ttft_n"] else None),
            "cache_hit_ratio": (round(acc["cache_read_tokens"] / prompt, 4)
                                if prompt else None),
        }
    return out
