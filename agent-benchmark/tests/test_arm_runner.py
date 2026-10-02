# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for the N-arm runner (answer generation + judging)."""

import pytest
import agent_benchmarks.eval.arm_runner as arm_runner_mod
from agent_benchmarks.eval.arm_runner import ArmRunner
from agent_benchmarks.treatments import BaselineTreatment, SkillAgentTreatment, SkillTreatment
from agent_benchmarks.skills import load_skill
from agent_benchmarks.plugins import create_plugins, plugin_set_metadata, wrap_treatments


def _patch_llm(monkeypatch, captured):
    def fake_call(prompt, model, provider="openai", api_key=None, system=None, **kw):
        captured.append({"prompt": prompt, "system": system,
                         "cache_prefix": kw.get("cache_prefix")})
        return f"answer (system={'yes' if system else 'no'})", {
            "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15
        }

    monkeypatch.setattr(arm_runner_mod, "llm_call_with_usage", fake_call)


QUESTIONS = [
    {"id": "q1", "question": "How do I parallelize a loop?", "category": "usage"},
    {"id": "q2", "question": "How do I sum an array in parallel?"},
]


def test_arm_runner_generates_per_arm(monkeypatch, demo_skill):
    captured = []
    _patch_llm(monkeypatch, captured)

    skill = load_skill(demo_skill)
    runner = ArmRunner([BaselineTreatment(), SkillTreatment(skill)])
    records = runner.run("oneTBB", QUESTIONS, concurrency=1)

    assert len(records) == 2
    rec = records[0]
    assert set(rec["arms"].keys()) == {"baseline", "skill:demo-skill"}
    # baseline has no context, skill arm does
    assert rec["arms"]["baseline"]["context_chunks"] == []
    assert rec["arms"]["skill:demo-skill"]["context_chunks"]
    # 2 questions x 2 arms = 4 LLM calls
    assert len(captured) == 4


def test_arm_runner_requires_at_least_one_arm():
    import pytest
    with pytest.raises(ValueError):
        ArmRunner([])


class _FakeJudge:
    """Scores by answer length so arms get distinct, deterministic numbers."""

    model = "fake-judge"
    provider = "fake-provider"

    def score_answer(self, library_name, question, answer, context="", ground_truth=None):
        agg = 80 if context.strip() and context != "(No documentation retrieved)" else 60
        return {"aggregate": agg, "correctness": agg}


def test_arm_runner_judge_computes_deltas(monkeypatch, demo_skill):
    captured = []
    _patch_llm(monkeypatch, captured)

    skill = load_skill(demo_skill)
    runner = ArmRunner([BaselineTreatment(), SkillTreatment(skill)])
    records = runner.run("oneTBB", QUESTIONS, concurrency=1)

    evaluations = runner.judge(_FakeJudge(), "oneTBB", records, baseline_arm="baseline")
    assert len(evaluations) == 2
    ev = evaluations[0]
    assert ev["scores"]["baseline"]["aggregate"] == 60
    assert ev["scores"]["skill:demo-skill"]["aggregate"] == 80
    assert ev["deltas_vs_baseline"]["skill:demo-skill"] == 20.0

    output = runner.build_output(
        "oneTBB", records, evaluations, baseline_arm="baseline", judge=_FakeJudge()
    )
    summary = output["summary"]["per_arm"]
    assert summary["baseline"]["avg_aggregate"] == 60.0
    assert summary["skill:demo-skill"]["delta_vs_baseline"] == 20.0
    assert output["judge_model"] == "fake-judge"
    assert output["judge_provider"] == "fake-provider"


def test_build_output_without_evaluations(monkeypatch):
    captured = []
    _patch_llm(monkeypatch, captured)
    runner = ArmRunner([BaselineTreatment()])
    records = runner.run("oneTBB", QUESTIONS[:1], concurrency=1)
    output = runner.build_output("oneTBB", records)
    assert "summary" not in output
    assert output["arms"] == ["baseline"]


def test_build_output_summarizes_skill_agent_discoverability(monkeypatch, demo_skill):
    import agent_benchmarks.eval.agent_runner as agent_runner_mod

    def fake_agent_loop(**kwargs):
        return {
            "answer": "used skill",
            "transcript": [{"iteration": 1, "tool": "view_skill_demo_skill"}],
            "tool_call_count": 1,
            "tool_usage": {
                "used_any_tool": True,
                "called_tools": ["view_skill_demo_skill"],
                "tool_call_count_by_name": {"view_skill_demo_skill": 1},
                "first_call_iteration_by_name": {"view_skill_demo_skill": 1},
                "skill": {
                    "offered": True,
                    "called": True,
                    "call_count": 1,
                    "first_call_iteration": 1,
                    "offered_tools": [{"name": "view_skill_demo_skill"}],
                },
            },
            "iterations": 2,
            "stopped_reason": "answered",
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            "token_usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            "per_turn": [],
        }

    monkeypatch.setattr(agent_runner_mod, "run_agent_loop", fake_agent_loop)

    skill = load_skill(demo_skill)
    runner = ArmRunner([SkillAgentTreatment(skill)])
    records = runner.run("oneTBB", QUESTIONS[:1], concurrency=1)
    arm = records[0]["arms"]["skill_agent:demo-skill"]
    assert arm["discoverability"]["called"] is True

    output = runner.build_output("oneTBB", records)
    usage = output["agentic_usage_summary"]["skill_agent:demo-skill"]
    assert usage["tool_use_rate"] == 1.0
    assert usage["skill_load_rate"] == 1.0
    assert usage["avg_skill_calls"] == 1.0


def test_arm_runner_emits_metrics_block_and_alias(monkeypatch):
    captured = []
    _patch_llm(monkeypatch, captured)
    runner = ArmRunner([BaselineTreatment()])
    records = runner.run("oneTBB", QUESTIONS[:1], concurrency=1)
    arm = records[0]["arms"]["baseline"]

    # Legacy alias preserved.
    assert arm["token_usage"] == {"prompt_tokens": 10, "completion_tokens": 5,
                                  "total_tokens": 15}
    # New metrics block present with required + optional fields.
    m = arm["metrics"]
    assert m["prompt_tokens"] == 10 and m["completion_tokens"] == 5
    assert m["total_tokens"] == 15
    assert m["cost_usd"] is None          # dict stub carries no pricing
    assert "latency_sec" in m and "ttft_sec" in m
    assert m["raw_answer_chars"] == m["final_answer_chars"]

    output = runner.build_output("oneTBB", records)
    cs = output["cost_summary"]["baseline"]
    assert cs["n"] == 1
    assert cs["total_tokens"] == 15
    assert cs["total_cost_usd"] is None
    assert cs["cost_known_n"] == 0   # dict stub has no pricing
    assert cs["mean_ttft_sec"] is None


def test_cost_summary_flags_partial_pricing_by_call():
    runner = ArmRunner([BaselineTreatment()])
    records = [{
        "arms": {
            "agent": {
                "metrics": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                    "cost_usd": 0.01,
                    "cost_known_calls": 1,
                    "n_calls": 2,
                    "latency_sec": 1.0,
                }
            }
        }
    }]

    cs = runner._cost_summary(records)["agent"]
    assert cs["total_cost_usd"] == 0.01
    assert cs["cost_known_n"] == 1
    assert cs["total_llm_calls"] == 2


def test_arm_runner_stamps_plugin_set_and_harness(monkeypatch):
    captured = []
    _patch_llm(monkeypatch, captured)
    plugins = create_plugins(["plugin:caveman"])
    plugin_set = plugin_set_metadata(plugins)
    treatments = wrap_treatments([BaselineTreatment()], plugins)

    runner = ArmRunner(
        treatments,
        harness="openclaw-agent",
        plugin_set=plugin_set,
        matrix_cell="agent-caveman",
    )
    records = runner.run("oneTBB", QUESTIONS[:1], concurrency=1)
    output = runner.build_output("oneTBB", records)

    assert "caveman style" in captured[0]["system"]
    assert records[0]["arms"]["baseline"]["plugin_set"] == "caveman:full"
    assert records[0]["arms"]["baseline"]["harness"] == "openclaw-agent"
    assert output["plugin_set"] == "caveman:full"
    assert output["harness"] == "openclaw-agent"
    assert output["matrix_cell"] == "agent-caveman"


def test_arm_runner_records_request_shaping_config(monkeypatch):
    captured = []
    _patch_llm(monkeypatch, captured)

    runner = ArmRunner(
        [BaselineTreatment()],
        max_tokens=32_000,
        max_iterations=9,
        grounded_from_topics=True,
    )
    records = runner.run("oneTBB", QUESTIONS[:1], concurrency=1)
    output = runner.build_output("oneTBB", records)

    # Without these a truncated run and a complete one are indistinguishable.
    assert output["run_config"] == {
        "max_tokens": 32_000,
        "max_iterations": 9,
        "grounded_from_topics": True,
    }


def test_arm_runner_run_config_defaults(monkeypatch):
    captured = []
    _patch_llm(monkeypatch, captured)

    runner = ArmRunner([BaselineTreatment()])
    output = runner.build_output(
        "oneTBB", runner.run("oneTBB", QUESTIONS[:1], concurrency=1)
    )

    assert output["run_config"]["max_tokens"] is None
    assert output["run_config"]["grounded_from_topics"] is False


def test_arm_runner_rejects_unknown_stats_correction():
    """A typo must fail at construction, not after a whole run is paid for."""
    with pytest.raises(ValueError, match="stats_correction"):
        ArmRunner([BaselineTreatment()], stats_correction="bonferroni")


def test_arm_runner_accepts_bh_correction_and_applies_it(monkeypatch):
    captured = []
    _patch_llm(monkeypatch, captured)
    runner = ArmRunner([BaselineTreatment()], stats_correction="bh")
    assert runner.stats_correction == "bh"

    evaluations = [
        {
            "question_id": f"q{i}",
            "scores": {"baseline": {"aggregate": 50.0 + i}, "docs": {"aggregate": 60.0 + i}},
        }
        for i in range(6)
    ]
    summary = runner._summarize(evaluations, "baseline")
    assert summary["per_arm"]["docs"]["significance"]["correction"] == "bh"


def _parse_arms_run(argv):
    from agent_benchmarks.cli import build_parser

    return build_parser().parse_args(
        ["arms", "run", "--product", "oneTBB",
         "--questions", "questions.json", "--arms", "baseline"] + argv
    )


def test_cli_defaults_stats_correction_to_holm():
    assert _parse_arms_run([]).stats_correction == "holm"


def test_cli_accepts_every_correction_stats_supports():
    """Guards against the CLI literal drifting from eval.stats.CORRECTIONS."""
    from agent_benchmarks.eval import stats

    for method in stats.CORRECTIONS:
        assert _parse_arms_run(["--stats-correction", method]).stats_correction == method


def test_cli_rejects_unknown_stats_correction():
    with pytest.raises(SystemExit):
        _parse_arms_run(["--stats-correction", "bonferroni"])


def test_matrix_run_also_exposes_stats_correction():
    """matrix-run copies the namespace wholesale, so the flag must exist there too."""
    from agent_benchmarks.cli import build_parser

    args = build_parser().parse_args(
        ["arms", "matrix-run", "--product", "oneTBB",
         "--questions", "questions.json", "--arms", "baseline",
         "--matrix-cells", "cells.json", "--stats-correction", "bh"]
    )
    assert args.stats_correction == "bh"


# ── cacheable prompt prefix ──────────────────────────────────────────────────


def test_context_precedes_the_question_in_the_prompt():
    """Providers only reuse a prefix, so the stable half has to come first."""
    from agent_benchmarks.eval.arm_runner import (
        ANSWER_PROMPT_WITH_CONTEXT,
        CONTEXT_PROMPT_PREFIX,
        CONTEXT_PROMPT_SUFFIX,
    )

    full = ANSWER_PROMPT_WITH_CONTEXT.format(question="Q?", context="CTX")
    assert full.index("CTX") < full.index("Q?")
    # The split must not introduce a third copy of the wording.
    assert full == (CONTEXT_PROMPT_PREFIX.format(context="CTX")
                    + CONTEXT_PROMPT_SUFFIX.format(question="Q?"))


def test_static_context_is_passed_as_a_cache_prefix(monkeypatch, demo_skill):
    """A skill body is identical for every question — a real cacheable prefix."""
    captured = []
    _patch_llm(monkeypatch, captured)

    skill = load_skill(demo_skill)
    runner = ArmRunner([SkillTreatment(skill)])
    runner.run("oneTBB", QUESTIONS, concurrency=1)

    prefixes = [c["cache_prefix"] for c in captured]
    assert all(p for p in prefixes)
    # Identical across questions — that is the whole point.
    assert len(set(prefixes)) == 1
    # And the question stays out of the cached half.
    assert QUESTIONS[0]["question"] not in prefixes[0]


def test_volatile_context_is_not_offered_for_caching(monkeypatch):
    """Query-driven retrieval would pay the write surcharge and never hit."""
    from agent_benchmarks.treatments import DocTreatment

    class _Client:
        def get_library_docs(self, library_id, query, max_results=5):
            return [{"content": f"chunk for {query}", "relevance_score": 0.9}]

    captured = []
    _patch_llm(monkeypatch, captured)
    runner = ArmRunner([DocTreatment(_Client())])
    runner.run("oneTBB", QUESTIONS, concurrency=1)

    assert [c["cache_prefix"] for c in captured] == [None, None]
    # Content is unchanged; it just travels as one string.
    assert "chunk for" in captured[0]["prompt"]


def test_baseline_arm_sends_no_prefix(monkeypatch):
    captured = []
    _patch_llm(monkeypatch, captured)
    ArmRunner([BaselineTreatment()]).run("oneTBB", QUESTIONS[:1], concurrency=1)
    assert captured[0]["cache_prefix"] is None
