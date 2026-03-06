"""Trust gate — answers the question "Can we trust this run?"

Checks a set of quality signals from eval output and emits
a structured verdict with per-check pass/fail reasons.

Designed to be called from the report generator; no side-effects.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ── Thresholds (can be overridden via spec/config) ────────────────────────────

DEFAULTS = {
    # Minimum number of evaluated questions for the run to be trusted
    "min_questions": 10,
    # Maximum fraction of questions with score == 0 (both modes)
    "max_zero_fraction": 0.20,
    # Minimum mean WITH-docs score (0-100)
    "min_with_docs_avg": 30.0,
    # Minimum delta (WITH minus WITHOUT); if docs don't help at all, suspicious
    "min_delta": -5.0,
    # Maximum coefficient of variation (std/mean) of WITH-docs scores — high CV = noisy
    "max_cv": 0.60,
    # Minimum inter-rater agreement fraction (when panel judge used)
    "min_agreement": 0.50,
    # Minimum fraction of questions where retrieval returned at least one doc
    "min_retrieval_hit_rate": 0.60,
    # Maximum allowed variance across multi-run scores (std of per-run WITH averages)
    "max_multirun_std": 5.0,
}


@dataclass
class TrustCheck:
    """Result of a single trust check."""

    name: str
    passed: bool
    value: Any
    threshold: Any
    message: str
    severity: str = "warn"  # "fail" | "warn" | "info"


@dataclass
class TrustVerdict:
    """Aggregate trust verdict for a run."""

    checks: List[TrustCheck] = field(default_factory=list)
    multirun_std: Optional[float] = None

    @property
    def trusted(self) -> bool:
        return all(c.passed for c in self.checks if c.severity == "fail")

    @property
    def warnings(self) -> List[TrustCheck]:
        return [c for c in self.checks if not c.passed and c.severity == "warn"]

    @property
    def failures(self) -> List[TrustCheck]:
        return [c for c in self.checks if not c.passed and c.severity == "fail"]

    @property
    def status(self) -> str:
        if self.failures:
            return "❌ FAIL"
        if self.warnings:
            return "⚠️ WARN"
        return "✅ PASS"


def evaluate_trust(
    evaluations: List[Dict[str, Any]],
    thresholds: Optional[Dict[str, Any]] = None,
    multirun_with_averages: Optional[List[float]] = None,
) -> TrustVerdict:
    """
    Compute trust verdict from a list of evaluation dicts.

    Args:
        evaluations:   List of eval entries (as stored in eval/{product}.json)
        thresholds:    Override any DEFAULTS key
        multirun_with_averages:  Per-run WITH-docs averages from N-run mode;
                                 if provided, variance check is included.
    Returns:
        TrustVerdict
    """
    cfg = {**DEFAULTS, **(thresholds or {})}
    checks: List[TrustCheck] = []

    valid = [
        e for e in evaluations
        if e.get("with_docs") and e["with_docs"].get("aggregate") is not None
        and e.get("without_docs") and e["without_docs"].get("aggregate") is not None
    ]

    # ── 1. Minimum question count ──────────────────────────────────────────
    n = len(valid)
    checks.append(TrustCheck(
        name="min_questions",
        passed=n >= cfg["min_questions"],
        value=n,
        threshold=cfg["min_questions"],
        message=f"{n} questions evaluated (min {cfg['min_questions']})",
        severity="fail",
    ))
    if n == 0:
        return TrustVerdict(checks=checks)  # can't compute anything else

    # ── 2. Zero-score fraction ─────────────────────────────────────────────
    zero_with = sum(1 for e in valid if e["with_docs"]["aggregate"] == 0)
    zero_frac = zero_with / n
    checks.append(TrustCheck(
        name="zero_score_fraction",
        passed=zero_frac <= cfg["max_zero_fraction"],
        value=round(zero_frac, 3),
        threshold=cfg["max_zero_fraction"],
        message=f"{zero_with}/{n} questions scored 0 WITH docs ({zero_frac:.1%})",
        severity="fail",
    ))

    # ── 3. Minimum WITH-docs average ──────────────────────────────────────
    with_scores = [e["with_docs"]["aggregate"] for e in valid]
    with_avg = statistics.mean(with_scores)
    checks.append(TrustCheck(
        name="min_with_docs_avg",
        passed=with_avg >= cfg["min_with_docs_avg"],
        value=round(with_avg, 1),
        threshold=cfg["min_with_docs_avg"],
        message=f"WITH-docs avg = {with_avg:.1f} (min {cfg['min_with_docs_avg']})",
        severity="warn",
    ))

    # ── 4. Minimum delta (WITH − WITHOUT) ─────────────────────────────────
    without_scores = [e["without_docs"]["aggregate"] for e in valid]
    delta_avg = statistics.mean(with_scores) - statistics.mean(without_scores)
    checks.append(TrustCheck(
        name="min_delta",
        passed=delta_avg >= cfg["min_delta"],
        value=round(delta_avg, 1),
        threshold=cfg["min_delta"],
        message=f"Avg delta (WITH−WITHOUT) = {delta_avg:+.1f} (min {cfg['min_delta']:+})",
        severity="warn",
    ))

    # ── 5. Score coefficient of variation (stability) ─────────────────────
    with_std = statistics.stdev(with_scores) if len(with_scores) > 1 else 0.0
    cv = (with_std / with_avg) if with_avg > 0 else 1.0
    checks.append(TrustCheck(
        name="score_cv",
        passed=cv <= cfg["max_cv"],
        value=round(cv, 3),
        threshold=cfg["max_cv"],
        message=f"Score CV = {cv:.2f} std={with_std:.1f} (max CV {cfg['max_cv']})",
        severity="warn",
    ))

    # ── 6. Inter-rater agreement (panel judge) ────────────────────────────
    agreement_scores = [
        e["with_docs"].get("agreement_score")
        for e in valid
        if isinstance(e.get("with_docs", {}).get("agreement_score"), (int, float))
    ]
    if agreement_scores:
        mean_agree = statistics.mean(agreement_scores)
        checks.append(TrustCheck(
            name="inter_rater_agreement",
            passed=mean_agree >= cfg["min_agreement"],
            value=round(mean_agree, 3),
            threshold=cfg["min_agreement"],
            message=f"Mean inter-rater agreement = {mean_agree:.2f} (min {cfg['min_agreement']})",
            severity="warn",
        ))

    # ── 7. Retrieval hit rate ─────────────────────────────────────────────
    # A question "hit" retrieval if with_docs answer is not "no relevant docs" fallback
    retrieval_hits = sum(
        1 for e in valid
        if e.get("with_docs", {}).get("retrieval_hit") is not False
        and e.get("with_docs", {}).get("aggregate", 0) > 0
    )
    hit_rate = retrieval_hits / n
    checks.append(TrustCheck(
        name="retrieval_hit_rate",
        passed=hit_rate >= cfg["min_retrieval_hit_rate"],
        value=round(hit_rate, 3),
        threshold=cfg["min_retrieval_hit_rate"],
        message=f"Retrieval hit rate = {hit_rate:.1%} ({retrieval_hits}/{n}) (min {cfg['min_retrieval_hit_rate']:.0%})",
        severity="warn",
    ))

    # ── 8. Multi-run variance (optional) ─────────────────────────────────
    multirun_std = None
    if multirun_with_averages and len(multirun_with_averages) >= 2:
        multirun_std = statistics.stdev(multirun_with_averages)
        checks.append(TrustCheck(
            name="multirun_variance",
            passed=multirun_std <= cfg["max_multirun_std"],
            value=round(multirun_std, 2),
            threshold=cfg["max_multirun_std"],
            message=(
                f"Multi-run WITH-docs std = {multirun_std:.2f} across {len(multirun_with_averages)} runs "
                f"(max {cfg['max_multirun_std']})"
            ),
            severity="fail",
        ))

    return TrustVerdict(checks=checks, multirun_std=multirun_std)


def format_trust_block(verdict: TrustVerdict) -> str:
    """Render the '## Can We Trust This Run?' markdown block."""
    lines = [
        "## Can We Trust This Run?",
        "",
        f"**Verdict: {verdict.status}**",
        "",
        "| Check | Status | Value | Threshold | Notes |",
        "|-------|--------|-------|-----------|-------|",
    ]
    for c in verdict.checks:
        icon = "✅" if c.passed else ("❌" if c.severity == "fail" else "⚠️")
        lines.append(
            f"| {c.name} | {icon} | {c.value} | {c.threshold} | {c.message} |"
        )
    if verdict.failures:
        lines += ["", "**Blocking issues:**"]
        for c in verdict.failures:
            lines.append(f"- ❌ **{c.name}**: {c.message}")
    if verdict.warnings:
        lines += ["", "**Warnings:**"]
        for c in verdict.warnings:
            lines.append(f"- ⚠️ **{c.name}**: {c.message}")
    lines.append("")
    return "\n".join(lines)
