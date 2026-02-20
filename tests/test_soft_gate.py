"""Tests for soft gate logic."""

import pytest
from doc_benchmarks.gate.soft_gate import check_soft_gate


def test_soft_gate_pass():
    """Score above threshold → PASS."""
    spec = {"future": {"soft_gate": {"enabled": True, "min_score": 0.80}}}
    result = check_soft_gate({"score": 0.85}, spec)
    
    assert result.enabled is True
    assert result.passed is True
    assert result.status == "PASS"
    assert result.min_score == 0.80
    assert result.actual_score == 0.85


def test_soft_gate_fail():
    """Score below threshold → FAIL."""
    spec = {"future": {"soft_gate": {"enabled": True, "min_score": 0.80}}}
    result = check_soft_gate({"score": 0.65}, spec)
    
    assert result.enabled is True
    assert result.passed is False
    assert result.status == "FAIL"


def test_soft_gate_exactly_at_threshold():
    """Score exactly at threshold → PASS."""
    spec = {"future": {"soft_gate": {"enabled": True, "min_score": 0.80}}}
    result = check_soft_gate({"score": 0.80}, spec)
    
    assert result.passed is True


def test_soft_gate_disabled():
    """Disabled gate → always PASS."""
    spec = {"future": {"soft_gate": {"enabled": False, "min_score": 0.95}}}
    result = check_soft_gate({"score": 0.10}, spec)
    
    assert result.enabled is False
    assert result.passed is True
    assert result.status == "DISABLED"


def test_soft_gate_missing_config():
    """Missing config → disabled."""
    spec = {}
    result = check_soft_gate({"score": 0.50}, spec)
    
    assert result.enabled is False
    assert result.passed is True


def test_soft_gate_empty_future():
    """Empty future section → disabled."""
    spec = {"future": {}}
    result = check_soft_gate({"score": 0.50}, spec)
    
    assert result.enabled is False
