"""Tests for critical bands enforcement."""

import pytest
from doc_benchmarks.gate.critical_bands import check_critical_bands


def test_critical_bands_pass():
    """All conditions met → no violations."""
    spec = {
        "critical_bands": {
            "fail_on": [
                {"condition": "score_below", "value": 0.60},
                {"condition": "coverage_below", "value": 0.70},
            ]
        }
    }
    summary = {"score": 0.75, "coverage": 0.80, "freshness_lite": 1.0, "readability": 1.0}
    
    result = check_critical_bands(summary, spec)
    
    assert result.enabled is True
    assert result.passed is True
    assert not result.has_violations


def test_critical_bands_violation():
    """Condition violated → has_violations."""
    spec = {
        "critical_bands": {
            "fail_on": [
                {"condition": "score_below", "value": 0.60},
                {"condition": "coverage_below", "value": 0.70},
            ]
        }
    }
    summary = {"score": 0.55, "coverage": 0.65, "freshness_lite": 1.0, "readability": 1.0}
    
    result = check_critical_bands(summary, spec)
    
    assert result.has_violations
    assert not result.passed
    assert len([v for v in result.violations if v.violated]) == 2


def test_critical_bands_exactly_at_threshold():
    """Value exactly at threshold → NOT violated."""
    spec = {
        "critical_bands": {
            "fail_on": [{"condition": "score_below", "value": 0.60}]
        }
    }
    summary = {"score": 0.60, "coverage": 1.0, "freshness_lite": 1.0, "readability": 1.0}
    
    result = check_critical_bands(summary, spec)
    
    assert result.passed


def test_critical_bands_disabled():
    """No fail_on list → disabled."""
    spec = {"critical_bands": {}}
    summary = {"score": 0.10, "coverage": 0.10, "freshness_lite": 0.0, "readability": 0.0}
    
    result = check_critical_bands(summary, spec)
    
    assert result.enabled is False
    assert result.passed


def test_critical_bands_unknown_condition():
    """Unknown condition → ValueError."""
    spec = {
        "critical_bands": {
            "fail_on": [{"condition": "typo_below", "value": 0.5}]
        }
    }
    summary = {"score": 0.70}
    
    with pytest.raises(ValueError, match="Unknown critical_bands condition"):
        check_critical_bands(summary, spec)


def test_critical_bands_missing_condition_key():
    """Missing 'condition' key → ValueError."""
    spec = {
        "critical_bands": {
            "fail_on": [{"value": 0.5}]
        }
    }
    summary = {"score": 0.70}
    
    with pytest.raises(ValueError, match="missing 'condition' key"):
        check_critical_bands(summary, spec)


def test_critical_bands_non_dict_entry():
    """Non-dict entry → ValueError."""
    spec = {
        "critical_bands": {
            "fail_on": ["score_below"]
        }
    }
    summary = {"score": 0.70}
    
    with pytest.raises(ValueError, match="must be mappings"):
        check_critical_bands(summary, spec)


def test_critical_bands_all_conditions():
    """Test all 4 supported conditions."""
    spec = {
        "critical_bands": {
            "fail_on": [
                {"condition": "score_below", "value": 0.80},
                {"condition": "coverage_below", "value": 0.75},
                {"condition": "freshness_below", "value": 0.70},
                {"condition": "readability_below", "value": 0.65},
            ]
        }
    }
    summary = {"score": 0.60, "coverage": 0.60, "freshness_lite": 0.60, "readability": 0.60}
    
    result = check_critical_bands(summary, spec)
    
    assert len(result.violations) == 4
    assert all(v.violated for v in result.violations)
