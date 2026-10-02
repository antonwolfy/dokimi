# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Novelty gate — soft checks over one ``novelty.v1`` artifact.

Every check here is **soft**: it reports and never blocks. That is a measured decision, not
caution. Subsampling the study's probes showed the cross-artifact ranking of `added` collapsing
below a 0.75 probe budget (Spearman 0.43-0.63 at 0.10), and a threshold at `added >= 0.15` flipped
its verdict on up to 24% of artifacts at a 0.25 budget. Correlating `added` against the measured
task delta pointed the same way from the other side: ranking 13 artifacts inside one model gave
-0.446, with the per-model correlations disagreeing in sign. So a novelty number is a profile of
one ``(artifact, model)`` pair, a threshold on it is an opinion about that pair's probe budget, and
nothing here may fail a build. ``severity`` is kept in the check because the posture is expected to
harden per-check once probe counts rise, not because anything is blocking today.

Thresholds come from the study; each one names the observation it came from.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ── Thresholds (override per call) ────────────────────────────────────────────

DEFAULTS: dict[str, Any] = {
    # Lenient `added` floor. The weakest artifact measured in the study sat at 0.131; below that an
    # artifact is mostly tokens. Lenient, not strict, because this is a floor and partial credit is
    # the generous reading — the *ranking* work is strict-only (lenient correlated at 0.126).
    "min_added_lenient": 0.15,
    # Dead-token ceiling. 11 of 13 analyzed skills sat at <=0.17; the two outliers (0.50, 0.74)
    # were a judging-cap artifact and are 0.068 and 0.064 on the full atom set (evidence §10.7).
    "max_frac_carrying_nothing": 0.25,
    # Share of atoms confirmed against the span cited for them. 0.907 was achievable with the
    # heading path prepended, and 0.19 of atoms were not recoverable from their cited file at all,
    # so this is set below the measured best rather than at it.
    "min_frac_located": 0.80,
    # Below this, a candidate's `value` is atom coverage per token wearing a value label.
    "min_value_coverage": 0.50,
}

# Every check ships at one of these severities. "fail" is unused on purpose (see module docstring).
SEVERITIES = ("info", "warn", "fail")


@dataclass
class NoveltyCheck:
    """One check against one novelty artifact."""

    name: str
    passed: bool
    value: Any
    threshold: Any
    message: str
    severity: str = "warn"
    measured: bool = True

    def as_dict(self) -> dict:
        """Serializable form (what the scorecard carries)."""
        return {
            "name": self.name,
            "measured": self.measured,
            "passed": self.passed,
            "value": self.value,
            "threshold": self.threshold,
            "message": self.message,
            "severity": self.severity,
        }


@dataclass
class NoveltyVerdict:
    """All checks for one ``(artifact, model)`` cell."""

    artifact_ref: str = ""
    model: str = ""
    checks: list[NoveltyCheck] = field(default_factory=list)

    @property
    def blocking(self) -> bool:
        """Always False today: no novelty check is hard. Kept so callers read the posture."""
        return any(not c.passed for c in self.checks if c.severity == "fail")

    @property
    def warnings(self) -> list[NoveltyCheck]:
        """Checks that did not pass at ``warn`` severity."""
        return [c for c in self.checks if not c.passed and c.severity == "warn"]

    @property
    def notes(self) -> list[NoveltyCheck]:
        """Checks that did not pass at ``info`` severity — observations, not problems."""
        return [c for c in self.checks if not c.passed and c.severity == "info"]

    @property
    def status(self) -> str:
        """``PASS`` / ``WARN`` / ``FAIL``, without a build meaning attached."""
        if self.blocking:
            return "FAIL"
        return "WARN" if self.warnings else "PASS"

    @property
    def not_measured(self) -> list[str]:
        """Checks whose input this run did not produce; they pass without having been run."""
        return [c.name for c in self.checks if not c.measured]

    def as_dict(self) -> dict:
        """Serializable form."""
        return {
            "artifact_ref": self.artifact_ref,
            "model": self.model,
            "status": self.status,
            "blocking": self.blocking,
            "not_measured": self.not_measured,
            "checks": [c.as_dict() for c in self.checks],
        }


def evaluate_novelty(artifact: dict, thresholds: dict[str, Any] | None = None) -> NoveltyVerdict:
    """Run the soft checks over one ``novelty.v1`` artifact.

    A check whose input the artifact does not carry passes with ``measured=False``, never as a
    silent pass: a run that skipped a stage must not read as a run that cleared it.
    """
    cfg = {**DEFAULTS, **(thresholds or {})}
    checks: list[NoveltyCheck] = []
    paired = artifact.get("paired", {}) or {}
    spans = artifact.get("spans", {}) or {}

    # ── 1. Is there enough new knowledge to be worth the tokens? ─────────────
    added = (paired.get("lenient") or {}).get("added")
    n_paired = (paired.get("lenient") or {}).get("n_paired", 0)
    if added is None or not n_paired:
        checks.append(NoveltyCheck(
            name="added_floor", passed=True, value=None, threshold=cfg["min_added_lenient"],
            severity="info", measured=False, message="no paired probes: `added` was not measured",
        ))
    else:
        checks.append(NoveltyCheck(
            name="added_floor",
            passed=added >= cfg["min_added_lenient"],
            value=round(added, 4), threshold=cfg["min_added_lenient"],
            message=(
                f"lenient `added` {added:.3f} over {n_paired} paired probes "
                f"(floor {cfg['min_added_lenient']}); this is one (artifact, model) pair and is "
                "not comparable to another artifact's figure"
            ),
        ))

    # ── 2. Does the artifact contradict itself or the model's correct prior? ──
    # The design asks for "no harmful atom on a rare-critical need path". novelty.v1 carries the
    # conflict count and the need-path classes separately, not joined per atom, so this checks the
    # count and says which of the two it is checking rather than implying the stronger one.
    categories = artifact.get("categories") or {}
    harmful = categories.get("harmful_conflicting", 0)
    degraded = (paired.get("strict") or {}).get("degraded")
    checks.append(NoveltyCheck(
        name="harmful_atoms",
        passed=not harmful,
        value=harmful if categories else None, threshold=0,
        severity="warn", measured=bool(categories),
        message=(
            f"{harmful} atoms classified harmful/conflicting"
            + (f"; strict `degraded` {degraded:.3f}" if degraded is not None else "")
            + ". Correctness gates before volume: one study skill carried 33 conflicts and still "
              "routed at 0.810, so it loads and misinforms"
        ),
    ))

    # ── 3. Dead weight, only when the atom set behind it was not capped ──────
    frac_dead = spans.get("frac_carrying_nothing")
    if frac_dead is None:
        checks.append(NoveltyCheck(
            name="dead_tokens", passed=True, value=None,
            threshold=cfg["max_frac_carrying_nothing"], severity="info", measured=False,
            message="dead-token share was not computed",
        ))
    elif spans.get("capped_atom_set"):
        checks.append(NoveltyCheck(
            name="dead_tokens", passed=True, value=round(frac_dead, 4),
            threshold=cfg["max_frac_carrying_nothing"], severity="info", measured=False,
            message=(
                f"not checked: the atom set was capped ({spans.get('n_atoms_indexed')} indexed), "
                "and a capped sample does not approximate this figure but inverts it — 0.064 read "
                "as 0.743 on the study's largest artifact"
            ),
        ))
    else:
        checks.append(NoveltyCheck(
            name="dead_tokens",
            passed=frac_dead <= cfg["max_frac_carrying_nothing"],
            value=round(frac_dead, 4), threshold=cfg["max_frac_carrying_nothing"],
            message=(
                f"{frac_dead:.3f} of tokens carry no extracted atom (ceiling "
                f"{cfg['max_frac_carrying_nothing']}); an upper bound on waste, not a measurement "
                "of it"
            ),
        ))

    # ── 4. No offered shortening may drop a protected span ──────────────────
    candidates = artifact.get("shortening") or []
    offered = [c for c in candidates if c.get("safe")]
    leaky = [c for c in offered if (c.get("protection") or 0) < 1.0]
    checks.append(NoveltyCheck(
        name="protection_invariant",
        passed=not leaky,
        value=len(leaky), threshold=0, measured=bool(candidates),
        message=(
            f"{len(leaky)} of {len(offered)} offered candidates drop a protected span. The study's "
            "worst candidate kept 0.916 of knowledge at 0.158 protection, which is why protection "
            "is pinned rather than averaged in"
        ),
    ))

    # ── 5. Are the span citations the views colour actually confirmed? ───────
    confirmation = (artifact.get("attribution") or {}).get("carrier_confirmation")
    if not confirmation:
        checks.append(NoveltyCheck(
            name="span_citations_confirmed", passed=True, value=None,
            threshold=cfg["min_frac_located"], severity="info", measured=False,
            message=(
                "span citations were not confirmed for this run, so the span views report the "
                "extractor's citation as given"
            ),
        ))
    else:
        located = confirmation.get("frac_located", 0.0)
        checks.append(NoveltyCheck(
            name="span_citations_confirmed",
            passed=located >= cfg["min_frac_located"],
            value=round(located, 4), threshold=cfg["min_frac_located"],
            message=(
                f"{confirmation.get('n_located')} of {confirmation.get('n_atoms')} atoms were "
                f"recovered from a span cited for them ({confirmation.get('n_unlocated')} "
                "unlocated). An unlocated atom is not wrong — in the study 46 of 49 were called "
                "supported — but no span may be coloured for it"
            ),
        ))

    # ── 6. Is `value` a measured axis on this run, or coverage in disguise? ──
    proxies = [c for c in candidates if c.get("value_is_coverage_proxy")]
    if not candidates:
        checks.append(NoveltyCheck(
            name="value_is_measured", passed=True, value=None, threshold=cfg["min_value_coverage"],
            severity="info", measured=False, message="no shortening candidates were ranked",
        ))
    else:
        coverages = [c.get("value_coverage") for c in candidates if c.get("value_coverage") is not None]
        worst = min(coverages) if coverages else None
        checks.append(NoveltyCheck(
            name="value_is_measured",
            passed=not proxies,
            value=None if worst is None else round(worst, 4),
            threshold=cfg["min_value_coverage"], severity="warn",
            message=(
                f"{len(proxies)} of {len(candidates)} candidates rank by value with value defined "
                "on under half their atoms, so the ranking is atom coverage per token; probe more "
                "atoms per artifact or read the `knowledge` column instead"
            ),
        ))

    # ── 7. Order independence — expected, and recorded rather than judged ───
    order_independent = (artifact.get("controls") or {}).get("order_independent")
    if order_independent is None:
        checks.append(NoveltyCheck(
            name="order_independence", passed=True, value=None, threshold=False,
            severity="info", measured=False, message="the shuffled control was not run",
        ))
    else:
        checks.append(NoveltyCheck(
            name="order_independence",
            passed=not order_independent,
            value=bool(order_independent), threshold=False, severity="info",
            message=(
                "the shuffled control scored at least as high as the artifact as written. Expected, "
                "not a defect: retested behaviourally on the tasks whose graded requirements name "
                "an ordering, scrambling span order cost +0.022 (CI -0.027 to +0.072). Spend "
                "authoring effort on facts and exact values, not on transitions"
            ),
        ))

    return NoveltyVerdict(
        artifact_ref=(artifact.get("artifact") or {}).get("ref", ""),
        model=artifact.get("model", ""),
        checks=checks,
    )


def format_novelty_block(verdicts: list[NoveltyVerdict]) -> str:
    """Render the ``## Novelty gate`` markdown block for one or more cells."""
    lines = ["## Novelty gate", "", "_All novelty checks are soft: they report and never block._"]
    if not verdicts:
        lines.extend(["", "- none"])
        return "\n".join(lines) + "\n"
    for verdict in verdicts:
        lines.extend([
            "",
            f"### `{verdict.artifact_ref or 'unknown'}` on `{verdict.model or 'unknown'}` "
            f"— {verdict.status}"
            + (f" ({len(verdict.not_measured)} of {len(verdict.checks)} not measured)" if verdict.not_measured else ""),
            "",
            "| Check | Status | Value | Threshold | Notes |",
            "| --- | --- | ---: | ---: | --- |",
        ])
        for check in verdict.checks:
            icon = "not measured" if not check.measured else (
                "ok" if check.passed else ("warn" if check.severity == "warn" else "note"))
            lines.append(
                f"| {check.name} | {icon} | {check.value} | {check.threshold} | {check.message} |"
            )
    return "\n".join(lines) + "\n"
