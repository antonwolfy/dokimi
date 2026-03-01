"""Tests for eval/panel.py — multi-judge panel with role-diverse judges."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from doc_benchmarks.eval.panel import (
    DEFAULT_PANEL,
    JUDGE_ROLES,
    ROLE_WEIGHTS,
    SCORE_FIELDS,
    JudgeConfig,
    JudgePanel,
    JudgeVote,
    PanelVerdict,
    _verdict_to_dict,
)

# _aggregate is a method on JudgePanel — expose via helper for unit tests
_panel_instance = JudgePanel.__new__(JudgePanel)
_panel_instance.judges = []


def _aggregate(votes):
    return _panel_instance._aggregate(votes)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_scores(value: float = 80.0) -> dict:
    return {k: value for k in SCORE_FIELDS}


def _make_vote(role="technical_expert", agg=80.0, error=None) -> JudgeVote:
    return JudgeVote(
        role=role, model="gpt-4o-mini", provider="openai",
        scores=_make_scores(agg), reasoning="ok", aggregate=agg, error=error,
    )


# ── ROLE_WEIGHTS & aggregate computation ──────────────────────────────────────

def test_role_weights_cover_all_roles():
    for role in DEFAULT_PANEL:
        assert role in ROLE_WEIGHTS, f"Missing weights for role: {role}"


def test_role_weights_cover_all_score_fields():
    for role, weights in ROLE_WEIGHTS.items():
        for field in SCORE_FIELDS:
            assert field in weights, f"Role '{role}' missing weight for '{field}'"


def test_compute_aggregate_uniform_scores():
    """Uniform scores → aggregate equals that score regardless of weights."""
    panel = JudgePanel()
    for role in DEFAULT_PANEL:
        agg = panel._compute_aggregate(role, _make_scores(70.0))
        assert abs(agg - 70.0) < 0.1, f"Role {role}: expected 70.0, got {agg}"


def test_compute_aggregate_correctness_heavy_for_expert():
    """technical_expert weights correctness 2x — high correctness raises aggregate."""
    panel = JudgePanel()
    scores_high_correct = {k: 50.0 for k in SCORE_FIELDS}
    scores_high_correct["correctness"] = 100.0
    agg = panel._compute_aggregate("technical_expert", scores_high_correct)
    # With correctness=100 and rest=50, weighted mean > 50
    assert agg > 55.0


def test_compute_aggregate_unknown_role_uses_equal_weights():
    panel = JudgePanel()
    agg = panel._compute_aggregate("unknown_role", _make_scores(60.0))
    assert abs(agg - 60.0) < 0.1


# ── PanelVerdict aggregation ──────────────────────────────────────────────────

def test_aggregate_empty_votes():
    verdict = _aggregate([])
    assert verdict.mean_aggregate is None
    assert verdict.std_aggregate is None
    assert verdict.agreement_score is None


def test_aggregate_single_vote():
    votes = [_make_vote(agg=75.0)]
    verdict = _aggregate(votes)
    assert verdict.mean_aggregate == 75.0
    assert verdict.std_aggregate == 0.0
    assert verdict.agreement_score == 1.0


def test_aggregate_multiple_votes_mean():
    votes = [_make_vote(agg=60.0), _make_vote(agg=80.0), _make_vote(agg=100.0)]
    verdict = _aggregate(votes)
    assert abs(verdict.mean_aggregate - 80.0) < 0.2


def test_aggregate_high_std_lowers_agreement():
    votes = [_make_vote(agg=0.0), _make_vote(agg=100.0)]
    verdict = _aggregate(votes)
    assert verdict.agreement_score is not None
    assert verdict.agreement_score < 0.5


def test_aggregate_low_std_high_agreement():
    votes = [_make_vote(agg=78.0), _make_vote(agg=80.0), _make_vote(agg=82.0)]
    verdict = _aggregate(votes)
    assert verdict.agreement_score is not None
    assert verdict.agreement_score > 0.8


def test_aggregate_disagreement_flag_large_std():
    votes = [_make_vote(agg=20.0), _make_vote(agg=90.0)]
    verdict = _aggregate(votes)
    assert verdict.disagreement_flag is True


def test_aggregate_no_disagreement_flag_small_std():
    votes = [_make_vote(agg=78.0), _make_vote(agg=82.0)]
    verdict = _aggregate(votes)
    assert verdict.disagreement_flag is False


def test_aggregate_skips_error_votes():
    votes = [_make_vote(agg=70.0), _make_vote(agg=None, error="API error")]
    verdict = _aggregate(votes)
    assert verdict.mean_aggregate == 70.0
    assert len(verdict.valid_votes) == 1


def test_aggregate_all_error_votes():
    votes = [_make_vote(agg=None, error="fail"), _make_vote(agg=None, error="fail")]
    verdict = _aggregate(votes)
    assert verdict.mean_aggregate is None


def test_aggregate_mean_dimensions():
    scores_a = {k: 60.0 for k in SCORE_FIELDS}
    scores_b = {k: 80.0 for k in SCORE_FIELDS}
    votes = [
        JudgeVote("technical_expert", "m", "p", scores_a, "", 60.0),
        JudgeVote("doc_reviewer", "m", "p", scores_b, "", 80.0),
    ]
    verdict = _aggregate(votes)
    for dim in SCORE_FIELDS:
        assert abs(verdict.mean_dimensions[dim] - 70.0) < 0.2


# ── JudgePanel._call_judge ────────────────────────────────────────────────────

FAKE_LLM_RESPONSE = json.dumps({
    "reasoning": "Good answer",
    "correctness": 80, "completeness": 75, "specificity": 70,
    "code_quality": 90, "actionability": 85,
})


def test_call_judge_success():
    panel = JudgePanel()
    cfg = JudgeConfig(role="technical_expert", model="gpt-4o-mini", provider="openai")
    with patch("doc_benchmarks.eval.panel.llm_call", return_value=FAKE_LLM_RESPONSE):
        vote = panel._call_judge(cfg, "How to use TBB?", "Use parallel_for.", "oneTBB", "")
    assert vote.error is None
    assert vote.scores["correctness"] == 80.0
    assert vote.aggregate is not None
    assert 0.0 <= vote.aggregate <= 100.0


def test_call_judge_clamps_scores():
    """Scores outside 0-100 should be clamped."""
    panel = JudgePanel()
    cfg = JudgeConfig(role="developer_advocate", model="gpt-4o-mini", provider="openai")
    out_of_range = json.dumps({
        "reasoning": "test", "correctness": 150, "completeness": -10,
        "specificity": 80, "code_quality": 80, "actionability": 80,
    })
    with patch("doc_benchmarks.eval.panel.llm_call", return_value=out_of_range):
        vote = panel._call_judge(cfg, "q", "a", "oneTBB", "")
    assert vote.scores["correctness"] == 100.0
    assert vote.scores["completeness"] == 0.0


def test_call_judge_error_returns_error_vote():
    panel = JudgePanel()
    cfg = JudgeConfig(role="doc_reviewer", model="gpt-4o-mini", provider="openai")
    with patch("doc_benchmarks.eval.panel.llm_call", side_effect=RuntimeError("API down")):
        vote = panel._call_judge(cfg, "q", "a", "oneTBB", "")
    assert vote.error == "API down"
    assert vote.aggregate is None


# ── JudgePanel.evaluate ───────────────────────────────────────────────────────

def test_evaluate_runs_all_judges():
    panel = JudgePanel(judges=[
        JudgeConfig("technical_expert", "gpt-4o-mini", "openai"),
        JudgeConfig("developer_advocate", "claude-sonnet-4", "anthropic"),
        JudgeConfig("doc_reviewer", "gemini-2.0-flash", "google"),
    ])
    with patch("doc_benchmarks.eval.panel.llm_call", return_value=FAKE_LLM_RESPONSE):
        verdict = panel.evaluate("How to schedule tasks?", "Use task_group.", "oneTBB")
    assert len(verdict.votes) == 3
    assert verdict.mean_aggregate is not None


def test_evaluate_gemini_provider_accepted():
    """Gemini provider config should not raise on construction."""
    cfg = JudgeConfig(role="doc_reviewer", model="gemini-2.0-flash", provider="google")
    panel = JudgePanel(judges=[cfg])
    with patch("doc_benchmarks.eval.panel.llm_call", return_value=FAKE_LLM_RESPONSE):
        verdict = panel.evaluate("q", "a", "oneTBB")
    assert verdict.mean_aggregate is not None


# ── _verdict_to_dict ──────────────────────────────────────────────────────────

def test_verdict_to_dict_none():
    assert _verdict_to_dict(None) is None


def test_verdict_to_dict_structure():
    verdict = PanelVerdict(
        votes=[_make_vote()], mean_aggregate=80.0, std_aggregate=0.0,
        agreement_score=1.0, mean_dimensions={k: 80.0 for k in SCORE_FIELDS},
    )
    d = _verdict_to_dict(verdict)
    assert d["aggregate"] == 80.0
    assert d["std"] == 0.0
    assert d["agreement_score"] == 1.0
    assert "votes" in d
    assert "dimensions" in d


# ── evaluate_answers end-to-end ───────────────────────────────────────────────

def _fake_answers(n=2):
    return [
        {
            "question_id": f"q{i}",
            "question": f"Question {i}?",
            "with_docs": {"answer": f"Answer {i} with docs.", "retrieved_docs": []},
            "without_docs": {"answer": f"Answer {i} without docs."},
        }
        for i in range(n)
    ]


def test_evaluate_answers_returns_all():
    panel = JudgePanel()
    with patch("doc_benchmarks.eval.panel.llm_call", return_value=FAKE_LLM_RESPONSE):
        results = panel.evaluate_answers(_fake_answers(3), library_name="oneTBB")
    assert len(results) == 3


def test_evaluate_answers_structure():
    panel = JudgePanel()
    with patch("doc_benchmarks.eval.panel.llm_call", return_value=FAKE_LLM_RESPONSE):
        results = panel.evaluate_answers(_fake_answers(1), library_name="oneTBB")
    r = results[0]
    assert "question_id" in r
    assert "with_docs" in r
    assert "without_docs" in r
    assert "delta" in r
    assert r["panel_size"] == len(DEFAULT_PANEL)


def test_evaluate_answers_delta_zero_when_same_score():
    """Same mocked LLM response → same score → delta ≈ 0."""
    panel = JudgePanel()
    with patch("doc_benchmarks.eval.panel.llm_call", return_value=FAKE_LLM_RESPONSE):
        results = panel.evaluate_answers(_fake_answers(1), library_name="oneTBB")
    assert results[0]["delta"] == 0.0


def test_evaluate_answers_incremental_save(tmp_path):
    panel = JudgePanel()
    out = tmp_path / "eval_panel.json"
    with patch("doc_benchmarks.eval.panel.llm_call", return_value=FAKE_LLM_RESPONSE):
        panel.evaluate_answers(_fake_answers(2), library_name="oneTBB", output_path=out)
    assert out.exists()
    data = json.loads(out.read_text())
    assert data["total_evaluations"] == 2
    assert "panel_config" in data


def test_evaluate_answers_limit(tmp_path):
    panel = JudgePanel()
    with patch("doc_benchmarks.eval.panel.llm_call", return_value=FAKE_LLM_RESPONSE):
        results = panel.evaluate_answers(_fake_answers(5), library_name="oneTBB", limit=2)
    assert len(results) == 2
