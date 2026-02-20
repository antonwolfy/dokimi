"""Tests for hard gate logic."""

import pytest
from doc_benchmarks.gate.hard_gate import check_hard_gate


def test_hard_gate_pass():
    """Score above threshold → PASS."""
    spec = {"future": {"hard_gate": {"enabled": True, "min_score": 0.85}}}
    result = check_hard_gate({"score": 0.90}, spec)
    
    assert result.enabled is True
    assert result.passed is True
    assert result.status == "PASS"


def test_hard_gate_fail():
    """Score below threshold → FAIL."""
    spec = {"future": {"hard_gate": {"enabled": True, "min_score": 0.85}}}
    result = check_hard_gate({"score": 0.70}, spec)
    
    assert result.enabled is True
    assert result.passed is False
    assert result.status == "FAIL"


def test_hard_gate_disabled():
    """Disabled gate → always PASS."""
    spec = {"future": {"hard_gate": {"enabled": False, "min_score": 0.99}}}
    result = check_hard_gate({"score": 0.10}, spec)
    
    assert result.enabled is False
    assert result.passed is True


def test_hard_gate_exactly_at_threshold():
    """Score exactly at threshold → PASS."""
    spec = {"future": {"hard_gate": {"enabled": True, "min_score": 0.85}}}
    result = check_hard_gate({"score": 0.85}, spec)
    
    assert result.passed is True
