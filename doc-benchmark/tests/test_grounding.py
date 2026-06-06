"""Tests for grounding/citation metrics and bootstrap CIs."""

from __future__ import annotations

from doc_benchmarks.eval.grounding import evaluate_grounding, grounding_score
from doc_benchmarks.eval.stats import bootstrap_ci


def test_grounding_score_full_overlap():
    assert grounding_score("parallel_for scheduler", ["the parallel_for scheduler docs"]) == 1.0


def test_grounding_score_no_overlap():
    assert grounding_score("zzz qqq", ["completely different content"]) == 0.0


def test_grounding_score_empty():
    assert grounding_score("", ["ctx"]) == 0.0
    assert grounding_score("answer", []) == 0.0


def test_evaluate_grounding_aggregates():
    answers = [
        {"question_id": "q1", "with_docs": {"answer": "use parallel_for",
                                            "retrieved_docs": [{"snippet": "parallel_for runs tasks"}]}},
        {"question_id": "q2", "with_docs": {"answer": "totally unrelated xyzzy",
                                            "retrieved_docs": [{"content": "documentation about scheduling"}]}},
        # skipped: no contexts
        {"question_id": "q3", "with_docs": {"answer": "no context", "retrieved_docs": []}},
    ]
    result = evaluate_grounding(answers, threshold=0.5)
    assert result["summary"]["n_evaluated"] == 2
    assert result["summary"]["grounding_score"]["n"] == 2
    assert 0.0 <= result["summary"]["citation_rate"] <= 1.0
    assert result["schema_version"] == "grounding.v1"
    ids = {p["question_id"] for p in result["per_question"]}
    assert ids == {"q1", "q2"}


def test_bootstrap_ci_basic():
    ci = bootstrap_ci([0.5, 0.5, 0.5, 0.5], seed=1)
    assert ci["mean"] == 0.5
    assert ci["lo"] == 0.5 and ci["hi"] == 0.5
    assert ci["n"] == 4


def test_bootstrap_ci_deterministic():
    vals = [0.1, 0.4, 0.6, 0.9, 0.3, 0.7]
    assert bootstrap_ci(vals, seed=42) == bootstrap_ci(vals, seed=42)


def test_bootstrap_ci_edge_cases():
    assert bootstrap_ci([])["mean"] is None
    one = bootstrap_ci([0.7])
    assert one["mean"] == one["lo"] == one["hi"] == 0.7


def test_bootstrap_ci_interval_brackets_mean():
    vals = [0.2, 0.4, 0.6, 0.8]
    ci = bootstrap_ci(vals, seed=3)
    assert ci["lo"] <= ci["mean"] <= ci["hi"]
