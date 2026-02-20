"""Hard gate checking — fails CI on violation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class HardGateResult:
    """Hard gate check result."""

    enabled: bool
    min_score: float
    actual_score: float
    passed: bool

    @property
    def status(self) -> str:
        """Human-readable status."""
        if not self.enabled:
            return "DISABLED"
        return "PASS" if self.passed else "FAIL"


def check_hard_gate(summary: dict, spec: dict) -> HardGateResult:
    """Check if summary passes hard gate threshold.
    
    Returns HardGateResult. Caller decides whether to exit.
    """
    gate_cfg = spec.get("future", {}).get("hard_gate", {})
    enabled = bool(gate_cfg.get("enabled", False))
    min_score = float(gate_cfg.get("min_score", 0.0))
    actual = float(summary.get("score", 0.0))

    passed = actual >= min_score if enabled else True

    return HardGateResult(
        enabled=enabled,
        min_score=min_score,
        actual_score=actual,
        passed=passed,
    )
