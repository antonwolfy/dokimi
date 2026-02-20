"""Tests for regression detection."""

import pytest
from doc_benchmarks.gate.regression import detect_regressions


def test_regression_ok():
    """No regression → all OK."""
    spec = {
        "thresholds": {
            "regressions": {
                "score_drop_warn": 0.03,
                "score_drop_critical": 0.08,
                "metric_drop_warn": 0.05,
                "metric_drop_critical": 0.12,
            }
        }
    }
    diff = {"score": 0.01, "coverage": 0.02, "freshness_lite": 0.00, "readability": -0.01}
    
    result = detect_regressions(diff, spec)
    
    assert result.score_regression.severity == "OK"
    assert not result.has_warnings
    assert not result.has_critical


def test_regression_warn():
    """Drop exceeds warn threshold → WARN."""
    spec = {
        "thresholds": {
            "regressions": {
                "score_drop_warn": 0.03,
                "score_drop_critical": 0.08,
                "metric_drop_warn": 0.05,
                "metric_drop_critical": 0.12,
            }
        }
    }
    diff = {"score": -0.05, "coverage": -0.06, "freshness_lite": 0.00, "readability": 0.00}
    
    result = detect_regressions(diff, spec)
    
    assert result.score_regression.severity == "WARN"
    assert result.metric_regressions[0].severity == "WARN"  # coverage
    assert result.has_warnings
    assert not result.has_critical


def test_regression_critical():
    """Drop exceeds critical threshold → CRITICAL."""
    spec = {
        "thresholds": {
            "regressions": {
                "score_drop_warn": 0.03,
                "score_drop_critical": 0.08,
                "metric_drop_warn": 0.05,
                "metric_drop_critical": 0.12,
            }
        }
    }
    diff = {"score": -0.10, "coverage": -0.15, "freshness_lite": 0.00, "readability": 0.00}
    
    result = detect_regressions(diff, spec)
    
    assert result.score_regression.severity == "CRITICAL"
    assert result.metric_regressions[0].severity == "CRITICAL"
    assert result.has_critical


def test_regression_exactly_at_threshold():
    """Drop exactly at threshold → WARN."""
    spec = {
        "thresholds": {
            "regressions": {
                "score_drop_warn": 0.03,
                "score_drop_critical": 0.08,
                "metric_drop_warn": 0.05,
                "metric_drop_critical": 0.12,
            }
        }
    }
    diff = {"score": -0.03, "coverage": 0.00, "freshness_lite": 0.00, "readability": 0.00}
    
    result = detect_regressions(diff, spec)
    
    assert result.score_regression.severity == "WARN"


def test_regression_improvement():
    """Positive delta → OK."""
    spec = {
        "thresholds": {
            "regressions": {
                "score_drop_warn": 0.03,
                "score_drop_critical": 0.08,
                "metric_drop_warn": 0.05,
                "metric_drop_critical": 0.12,
            }
        }
    }
    diff = {"score": 0.10, "coverage": 0.05, "freshness_lite": 0.00, "readability": 0.00}
    
    result = detect_regressions(diff, spec)
    
    assert result.score_regression.severity == "OK"
    assert not result.has_warnings


def test_regression_missing_thresholds():
    """Missing thresholds → use defaults (0.03 warn, 0.08 critical)."""
    spec = {}
    # -0.01 drop < 0.03 default warn threshold → OK
    diff = {"score": -0.01, "coverage": 0.00, "freshness_lite": 0.00, "readability": 0.00}
    
    result = detect_regressions(diff, spec)
    
    assert result.score_regression.severity == "OK"  # -0.01 < 0.03 warn threshold
