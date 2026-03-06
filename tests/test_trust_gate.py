"""Tests for trust gate — 'Can we trust this run?' check."""
import pytest
from doc_benchmarks.gate.trust_gate import (
    evaluate_trust,
    format_trust_block,
    TrustVerdict,
    DEFAULTS,
)


def _make_eval(with_score=70.0, without_score=50.0, agree=0.8):
    return {
        "question_id": "q_001",
        "with_docs": {"aggregate": with_score, "agreement_score": agree},
        "without_docs": {"aggregate": without_score},
        "delta": with_score - without_score,
    }


def _evals(n=20, with_score=70.0, without_score=50.0):
    return [_make_eval(with_score, without_score) for _ in range(n)]


class TestMinQuestions:
    def test_passes_with_enough(self):
        v = evaluate_trust(_evals(20))
        check = next(c for c in v.checks if c.name == "min_questions")
        assert check.passed

    def test_fails_with_too_few(self):
        v = evaluate_trust(_evals(5))
        check = next(c for c in v.checks if c.name == "min_questions")
        assert not check.passed
        assert check.severity == "fail"

    def test_empty_evals_only_min_q_check(self):
        v = evaluate_trust([])
        assert len(v.checks) == 1
        assert not v.checks[0].passed


class TestZeroScoreFraction:
    def test_passes_low_zero_fraction(self):
        evals = _evals(20, with_score=70)
        evals[0]["with_docs"]["aggregate"] = 0
        v = evaluate_trust(evals)
        check = next(c for c in v.checks if c.name == "zero_score_fraction")
        assert check.passed  # 1/20 = 5%

    def test_fails_high_zero_fraction(self):
        evals = _evals(10, with_score=0)  # all zeros
        v = evaluate_trust(evals)
        check = next(c for c in v.checks if c.name == "zero_score_fraction")
        assert not check.passed


class TestWithDocsAvg:
    def test_passes_above_threshold(self):
        v = evaluate_trust(_evals(15, with_score=60))
        check = next(c for c in v.checks if c.name == "min_with_docs_avg")
        assert check.passed

    def test_warns_below_threshold(self):
        v = evaluate_trust(_evals(15, with_score=20))
        check = next(c for c in v.checks if c.name == "min_with_docs_avg")
        assert not check.passed
        assert check.severity == "warn"


class TestDeltaCheck:
    def test_passes_positive_delta(self):
        v = evaluate_trust(_evals(15, with_score=70, without_score=50))
        check = next(c for c in v.checks if c.name == "min_delta")
        assert check.passed

    def test_warns_on_large_negative_delta(self):
        v = evaluate_trust(_evals(15, with_score=30, without_score=60))
        check = next(c for c in v.checks if c.name == "min_delta")
        assert not check.passed


class TestMultiRunVariance:
    def test_low_variance_passes(self):
        v = evaluate_trust(_evals(15), multirun_with_averages=[70.0, 71.0, 70.5])
        check = next(c for c in v.checks if c.name == "multirun_variance")
        assert check.passed

    def test_high_variance_fails(self):
        v = evaluate_trust(_evals(15), multirun_with_averages=[70.0, 50.0, 90.0])
        check = next(c for c in v.checks if c.name == "multirun_variance")
        assert not check.passed
        assert check.severity == "fail"

    def test_single_run_no_variance_check(self):
        v = evaluate_trust(_evals(15), multirun_with_averages=[70.0])
        names = [c.name for c in v.checks]
        assert "multirun_variance" not in names


class TestTrustVerdict:
    def test_trusted_all_pass(self):
        v = evaluate_trust(_evals(20, with_score=70, without_score=50))
        assert v.trusted

    def test_not_trusted_fail_severity(self):
        v = evaluate_trust(_evals(5))  # fails min_questions (fail severity)
        assert not v.trusted

    def test_status_pass(self):
        v = evaluate_trust(_evals(20, with_score=70, without_score=50))
        assert v.status == "✅ PASS"

    def test_status_warn(self):
        v = evaluate_trust(_evals(15, with_score=20, without_score=15))
        # with_avg=20 below min 30 → warn; no fail severities
        assert "WARN" in v.status or "FAIL" in v.status


class TestCustomThresholds:
    def test_custom_min_questions(self):
        v = evaluate_trust(_evals(5), thresholds={"min_questions": 3})
        check = next(c for c in v.checks if c.name == "min_questions")
        assert check.passed

    def test_custom_max_zero_fraction(self):
        evals = _evals(10, with_score=0)
        v = evaluate_trust(evals, thresholds={"max_zero_fraction": 1.0})
        check = next(c for c in v.checks if c.name == "zero_score_fraction")
        assert check.passed


class TestFormatTrustBlock:
    def test_renders_markdown(self):
        v = evaluate_trust(_evals(20, with_score=70, without_score=50))
        md = format_trust_block(v)
        assert "## Can We Trust This Run?" in md
        assert "✅ PASS" in md or "⚠️ WARN" in md or "❌ FAIL" in md
        assert "| Check |" in md

    def test_shows_failures(self):
        v = evaluate_trust(_evals(5))  # fails min_questions
        md = format_trust_block(v)
        assert "Blocking issues" in md
        assert "min_questions" in md
