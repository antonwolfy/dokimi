"""Tests for failure diagnoser."""

import pytest
from doc_benchmarks.eval.diagnoser import (
    diagnose,
    summarise_diagnoses,
    DOCS_HELPED,
    EMPTY_RETRIEVAL,
    BELOW_THRESHOLD,
    LOW_RELEVANCE,
    KNOWLEDGE_SUFFICIENT,
    INSUFFICIENT_DATA,
)


def _make_answer(doc_source="context7", retrieved_docs=None):
    return {
        "with_docs": {
            "doc_source": doc_source,
            "retrieved_docs": retrieved_docs or [],
        },
        "without_docs": {"answer": "some answer"},
    }


def _make_eval(delta):
    return {"delta": delta}


# ── diagnose() ────────────────────────────────────────────────────────────────

def test_docs_helped_positive_delta():
    result = diagnose(_make_answer(), _make_eval(delta=5.0))
    assert result["label"] == DOCS_HELPED


def test_docs_helped_zero_delta():
    result = diagnose(_make_answer(), _make_eval(delta=0.0))
    assert result["label"] == DOCS_HELPED


def test_insufficient_data_no_delta():
    result = diagnose(_make_answer(), _make_eval(delta=None))
    assert result["label"] == INSUFFICIENT_DATA


def test_empty_retrieval_no_docs():
    answer = _make_answer(doc_source="fallback_none", retrieved_docs=[])
    result = diagnose(answer, _make_eval(delta=-3.0))
    assert result["label"] == EMPTY_RETRIEVAL


def test_empty_retrieval_no_mcp_client():
    answer = _make_answer(doc_source="none", retrieved_docs=[])
    result = diagnose(answer, _make_eval(delta=-2.0))
    assert result["label"] == EMPTY_RETRIEVAL
    assert result["evidence"].get("reason") == "no_mcp_client"


def test_low_relevance():
    docs = [{"relevance_score": 0.1}, {"relevance_score": 0.05}]
    answer = _make_answer(doc_source="context7", retrieved_docs=docs)
    result = diagnose(answer, _make_eval(delta=-4.0))
    assert result["label"] == LOW_RELEVANCE
    assert result["evidence"]["top_relevance_score"] == pytest.approx(0.1)


def test_knowledge_sufficient_high_relevance():
    docs = [{"relevance_score": 0.8}, {"relevance_score": 0.6}]
    answer = _make_answer(doc_source="context7", retrieved_docs=docs)
    result = diagnose(answer, _make_eval(delta=-2.0))
    assert result["label"] == KNOWLEDGE_SUFFICIENT
    assert result["evidence"]["top_relevance_score"] == pytest.approx(0.8)


def test_knowledge_sufficient_no_score_field():
    """Docs without relevance_score → treated as knowledge_sufficient (not low_relevance)."""
    docs = [{"content": "some content"}]  # no relevance_score
    answer = _make_answer(doc_source="context7", retrieved_docs=docs)
    result = diagnose(answer, _make_eval(delta=-1.0))
    assert result["label"] == KNOWLEDGE_SUFFICIENT


def test_diagnosis_has_required_keys():
    answer = _make_answer(doc_source="fallback_none")
    result = diagnose(answer, _make_eval(delta=-1.0))
    assert "label" in result
    assert "detail" in result
    assert "evidence" in result
    assert isinstance(result["detail"], str)
    assert len(result["detail"]) > 0


def test_custom_cutoff():
    """Custom cutoff: score=0.4 should be low_relevance when cutoff=0.5."""
    docs = [{"relevance_score": 0.4}]
    answer = _make_answer(doc_source="context7", retrieved_docs=docs)
    result = diagnose(answer, _make_eval(delta=-1.0), low_relevance_cutoff=0.5)
    assert result["label"] == LOW_RELEVANCE


# ── summarise_diagnoses() ─────────────────────────────────────────────────────

def _eval_with_diagnosis(delta, label):
    diag = {"label": label, "detail": "", "evidence": {}}
    return {"delta": delta, "diagnosis": diag, "question_id": f"q-{label}"}


def test_summarise_counts():
    evals = [
        _eval_with_diagnosis(2.0, DOCS_HELPED),
        _eval_with_diagnosis(-1.0, EMPTY_RETRIEVAL),
        _eval_with_diagnosis(-2.0, LOW_RELEVANCE),
        _eval_with_diagnosis(-3.0, KNOWLEDGE_SUFFICIENT),
    ]
    summary = summarise_diagnoses(evals)
    assert summary["total"] == 4
    assert summary["counts"][DOCS_HELPED] == 1
    assert summary["counts"][EMPTY_RETRIEVAL] == 1
    assert summary["counts"][LOW_RELEVANCE] == 1
    assert summary["counts"][KNOWLEDGE_SUFFICIENT] == 1


def test_summarise_failures_list():
    evals = [
        _eval_with_diagnosis(5.0, DOCS_HELPED),
        _eval_with_diagnosis(-2.0, LOW_RELEVANCE),
    ]
    summary = summarise_diagnoses(evals)
    assert len(summary["failures"]) == 1
    assert summary["failures"][0]["delta"] == -2.0


def test_summarise_rates_sum_to_one():
    evals = [_eval_with_diagnosis(1.0, DOCS_HELPED)] * 3 + \
            [_eval_with_diagnosis(-1.0, EMPTY_RETRIEVAL)]
    summary = summarise_diagnoses(evals)
    total_rate = sum(summary["rates"].values())
    assert total_rate == pytest.approx(1.0)


def test_summarise_empty_list():
    summary = summarise_diagnoses([])
    assert summary["total"] == 0
    assert all(v == 0 for v in summary["rates"].values())
