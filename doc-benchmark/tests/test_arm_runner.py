"""Tests for the N-arm runner (answer generation + judging)."""

import doc_benchmarks.eval.arm_runner as arm_runner_mod
from doc_benchmarks.eval.arm_runner import ArmRunner
from doc_benchmarks.treatments import BaselineTreatment, SkillTreatment
from doc_benchmarks.skills import load_skill


def _patch_llm(monkeypatch, captured):
    def fake_call(prompt, model, provider="openai", api_key=None, system=None, **kw):
        captured.append({"prompt": prompt, "system": system})
        return f"answer (system={'yes' if system else 'no'})", {
            "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15
        }

    monkeypatch.setattr(arm_runner_mod, "llm_call_with_usage", fake_call)


QUESTIONS = [
    {"id": "q1", "question": "How do I parallelize a loop?", "category": "usage"},
    {"id": "q2", "question": "How do I sum an array in parallel?"},
]


def test_arm_runner_generates_per_arm(monkeypatch):
    captured = []
    _patch_llm(monkeypatch, captured)

    skill = load_skill("data/skills/onetbb-quickstart")
    runner = ArmRunner([BaselineTreatment(), SkillTreatment(skill)])
    records = runner.run("oneTBB", QUESTIONS, concurrency=1)

    assert len(records) == 2
    rec = records[0]
    assert set(rec["arms"].keys()) == {"baseline", "skill:onetbb-quickstart"}
    # baseline has no context, skill arm does
    assert rec["arms"]["baseline"]["context_chunks"] == []
    assert rec["arms"]["skill:onetbb-quickstart"]["context_chunks"]
    # 2 questions x 2 arms = 4 LLM calls
    assert len(captured) == 4


def test_arm_runner_requires_at_least_one_arm():
    import pytest
    with pytest.raises(ValueError):
        ArmRunner([])


class _FakeJudge:
    """Scores by answer length so arms get distinct, deterministic numbers."""

    def score_answer(self, library_name, question, answer, context="", ground_truth=None):
        agg = 80 if context.strip() and context != "(No documentation retrieved)" else 60
        return {"aggregate": agg, "correctness": agg}


def test_arm_runner_judge_computes_deltas(monkeypatch):
    captured = []
    _patch_llm(monkeypatch, captured)

    skill = load_skill("data/skills/onetbb-quickstart")
    runner = ArmRunner([BaselineTreatment(), SkillTreatment(skill)])
    records = runner.run("oneTBB", QUESTIONS, concurrency=1)

    evaluations = runner.judge(_FakeJudge(), "oneTBB", records, baseline_arm="baseline")
    assert len(evaluations) == 2
    ev = evaluations[0]
    assert ev["scores"]["baseline"]["aggregate"] == 60
    assert ev["scores"]["skill:onetbb-quickstart"]["aggregate"] == 80
    assert ev["deltas_vs_baseline"]["skill:onetbb-quickstart"] == 20.0

    output = runner.build_output("oneTBB", records, evaluations, baseline_arm="baseline")
    summary = output["summary"]["per_arm"]
    assert summary["baseline"]["avg_aggregate"] == 60.0
    assert summary["skill:onetbb-quickstart"]["delta_vs_baseline"] == 20.0


def test_build_output_without_evaluations(monkeypatch):
    captured = []
    _patch_llm(monkeypatch, captured)
    runner = ArmRunner([BaselineTreatment()])
    records = runner.run("oneTBB", QUESTIONS[:1], concurrency=1)
    output = runner.build_output("oneTBB", records)
    assert "summary" not in output
    assert output["arms"] == ["baseline"]
