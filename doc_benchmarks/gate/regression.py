"""Regression detection and classification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Severity = Literal["OK", "WARN", "CRITICAL"]


@dataclass
class RegressionResult:
    """Single metric regression analysis."""

    metric: str
    delta: float
    severity: Severity
    threshold_warn: float
    threshold_critical: float


@dataclass
class RegressionSummary:
    """Overall regression analysis."""

    score_regression: RegressionResult
    metric_regressions: list[RegressionResult]

    @property
    def has_warnings(self) -> bool:
        """Any WARN-level regressions."""
        return any(
            r.severity == "WARN"
            for r in [self.score_regression] + self.metric_regressions
        )

    @property
    def has_critical(self) -> bool:
        """Any CRITICAL-level regressions."""
        return any(
            r.severity == "CRITICAL"
            for r in [self.score_regression] + self.metric_regressions
        )


def _classify_regression(
    delta: float, warn_threshold: float, critical_threshold: float
) -> Severity:
    """Classify a negative delta by threshold.
    
    Delta is expected to be negative for regressions.
    Thresholds are positive (how much drop is allowed).
    """
    if delta >= 0:
        return "OK"  # Improvement, not regression
    drop = abs(delta)
    if drop >= critical_threshold:
        return "CRITICAL"
    if drop >= warn_threshold:
        return "WARN"
    return "OK"


def detect_regressions(diff: dict, spec: dict) -> RegressionSummary:
    """Analyze compare diff for regressions.
    
    Returns RegressionSummary with classified deltas.
    """
    thresholds = spec.get("thresholds", {}).get("regressions", {})
    score_warn = float(thresholds.get("score_drop_warn", 0.03))
    score_crit = float(thresholds.get("score_drop_critical", 0.08))
    metric_warn = float(thresholds.get("metric_drop_warn", 0.05))
    metric_crit = float(thresholds.get("metric_drop_critical", 0.12))

    score_delta = float(diff.get("score", 0.0))
    score_result = RegressionResult(
        metric="score",
        delta=score_delta,
        severity=_classify_regression(score_delta, score_warn, score_crit),
        threshold_warn=score_warn,
        threshold_critical=score_crit,
    )

    metric_names = ["coverage", "freshness_lite", "readability", "example_pass_rate"]
    metric_results = []
    for name in metric_names:
        if name in diff:
            delta = float(diff[name])
            metric_results.append(
                RegressionResult(
                    metric=name,
                    delta=delta,
                    severity=_classify_regression(delta, metric_warn, metric_crit),
                    threshold_warn=metric_warn,
                    threshold_critical=metric_crit,
                )
            )

    return RegressionSummary(
        score_regression=score_result,
        metric_regressions=metric_results,
    )
