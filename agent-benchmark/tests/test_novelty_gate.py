# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""The novelty gate's soft checks, and the scorecard block built from them."""

from __future__ import annotations

import pytest

from agent_benchmarks.gate.novelty_gate import (
    evaluate_novelty,
    format_novelty_block,
)
from agent_benchmarks.subjects.novelty_track import (
    build_novelty_block,
    load_novelty_artifacts,
    novelty_warnings,
)


def _artifact(**overrides):
    """A healthy novelty artifact: every check passes, nothing is skipped."""
    artifact = {
        "artifact": {"ref": "skill:skills/accel-tuning", "kind": "skill"},
        "model": "m",
        "provider": "openai",
        "judge_model": "j",
        "atoms": {"n": 40, "n_probed": 40, "sampling": "all"},
        "paired": {
            "lenient": {"added": 0.42, "redundant": 0.5, "degraded": 0.0,
                        "still_missing": 0.08, "n_paired": 40, "ci95_added": [0.3, 0.55]},
            "strict": {"added": 0.30, "redundant": 0.6, "degraded": 0.0,
                       "still_missing": 0.10, "n_paired": 40, "ci95_added": [0.2, 0.4]},
        },
        "k0": {"lenient": 0.5, "strict": 0.6},
        "categories": {"harmful_conflicting": 0, "novel_useful": 30},
        "spans": {"n": 60, "tokens": 900, "frac_carrying_nothing": 0.12,
                  "capped_atom_set": False},
        "shortening": [{"safe": True, "protection": 1.0, "value_coverage": 0.9,
                        "value_is_coverage_proxy": False}],
        "attribution": {"carrier_confirmation": {"n_atoms": 40, "n_located": 38,
                                                 "n_unlocated": 2, "frac_located": 0.95}},
        "controls": {"order_independent": False},
        "warnings": [],
    }
    artifact.update(overrides)
    return artifact


def _named(verdict, name):
    return next(check for check in verdict.checks if check.name == name)


def test_a_healthy_artifact_passes_every_check():
    verdict = evaluate_novelty(_artifact())
    assert verdict.status == "PASS"
    assert verdict.blocking is False
    assert [check.name for check in verdict.checks if not check.passed] == []
    assert verdict.not_measured == []


def test_a_run_that_skipped_its_stages_says_so_instead_of_passing():
    # --no-classify --no-shorten --no-confirm-carriers, and no shuffled arm (the default arms).
    verdict = evaluate_novelty(_artifact(
        categories={}, shortening=[], attribution={}, controls={}, spans={"n": 60}))
    assert verdict.not_measured == [
        "harmful_atoms", "dead_tokens", "protection_invariant", "span_citations_confirmed",
        "value_is_measured", "order_independence",
    ]
    block = format_novelty_block([verdict])
    assert "(6 of 7 not measured)" in block
    assert "| harmful_atoms | not measured | None |" in block


@pytest.mark.parametrize("name, overrides", [
    ("added_floor", {"paired": {"lenient": {"added": 0.04, "n_paired": 40}}}),
    ("harmful_atoms", {"categories": {"harmful_conflicting": 3}}),
    ("dead_tokens", {"spans": {"frac_carrying_nothing": 0.74, "capped_atom_set": False}}),
    ("protection_invariant", {"shortening": [{"safe": True, "protection": 0.158}]}),
    ("span_citations_confirmed", {"attribution": {"carrier_confirmation": {
        "n_atoms": 40, "n_located": 20, "n_unlocated": 20, "frac_located": 0.5}}}),
    ("value_is_measured", {"shortening": [{"safe": True, "protection": 1.0,
                                           "value_coverage": 0.2,
                                           "value_is_coverage_proxy": True}]}),
])
def test_each_failing_check_warns_and_never_blocks(name, overrides):
    verdict = evaluate_novelty(_artifact(**overrides))
    check = _named(verdict, name)
    assert check.passed is False
    assert check.severity == "warn"
    assert verdict.status == "WARN"
    # The whole point of the gate: a novelty number is a profile, so nothing here stops a build.
    assert verdict.blocking is False


def test_a_capped_atom_set_skips_the_dead_token_check_instead_of_passing_it():
    verdict = evaluate_novelty(_artifact(
        spans={"frac_carrying_nothing": 0.743, "capped_atom_set": True, "n_atoms_indexed": 40}
    ))
    check = _named(verdict, "dead_tokens")
    assert (check.passed, check.severity) == (True, "info")
    assert "capped" in check.message
    assert verdict.status == "PASS"


def test_an_unconfirmed_run_is_reported_as_unchecked_not_as_confirmed():
    artifact = _artifact()
    artifact["attribution"] = {}
    check = _named(evaluate_novelty(artifact), "span_citations_confirmed")
    assert (check.passed, check.severity, check.value) == (True, "info", None)
    assert "not confirmed" in check.message


@pytest.mark.parametrize("paired", [
    {},
    {"lenient": {"added": 0.0, "redundant": 0.0, "degraded": 0.0, "still_missing": 0.0,
                 "n_paired": 0}},
])
def test_a_run_without_paired_probes_reports_added_as_unmeasured(paired):
    verdict = evaluate_novelty(_artifact(paired=paired))
    check = _named(verdict, "added_floor")
    assert (check.passed, check.severity, check.value) == (True, "info", None)
    assert "added_floor" in verdict.not_measured


def test_order_independence_is_recorded_as_a_note_not_a_defect():
    verdict = evaluate_novelty(_artifact(controls={"order_independent": True}))
    check = _named(verdict, "order_independence")
    assert (check.passed, check.severity) == (False, "info")
    assert verdict.status == "PASS"
    assert [c.name for c in verdict.notes] == ["order_independence"]


def test_thresholds_are_overridable_per_call():
    verdict = evaluate_novelty(_artifact(), thresholds={"min_added_lenient": 0.9})
    assert _named(verdict, "added_floor").passed is False


def test_the_gate_block_states_that_checks_never_block():
    block = format_novelty_block([evaluate_novelty(_artifact())])
    assert "## Novelty gate" in block
    assert "never block" in block
    assert "added_floor" in block
    assert "- none" in format_novelty_block([])


def test_the_scorecard_block_keeps_cells_and_never_averages_them():
    block = build_novelty_block(
        [_artifact(), _artifact(model="m2", paired={"lenient": {"added": 0.04, "n_paired": 9}})],
        sources=["a.json", "b.json"],
    )
    assert block["status"] == "measured"
    assert block["n_cells"] == 2
    assert [cell["model"] for cell in block["cells"]] == ["m", "m2"]
    assert [cell["source"] for cell in block["cells"]] == ["a.json", "b.json"]
    # No pooled figure anywhere: a mean over (artifact, model) cells would mix two effects.
    assert not any(key.startswith("mean") or key == "added" for key in block)
    assert any("-0.446" in caveat for caveat in block["caveats"])


def test_an_empty_novelty_block_is_not_run_rather_than_zero():
    block = build_novelty_block([])
    assert (block["status"], block["n_cells"], block["cells"]) == ("not_run", 0, [])


def test_cell_warnings_reach_the_subject_warning_list():
    block = build_novelty_block([_artifact(categories={"harmful_conflicting": 3})])
    warnings = novelty_warnings(block)
    assert len(warnings) == 1
    assert "harmful_atoms" in warnings[0]
    assert "skill:skills/accel-tuning" in warnings[0] and "on m" in warnings[0]
    # An info-severity note is not a subject warning.
    assert novelty_warnings(build_novelty_block([_artifact(attribution={})])) == []


def test_an_attached_artifact_must_validate(tmp_path):
    import json

    from agent_benchmarks.artifacts import ArtifactValidationError

    bad = tmp_path / "novelty.json"
    bad.write_text(json.dumps({"schema_version": "novelty.v1"}), encoding="utf-8")
    with pytest.raises(ArtifactValidationError):
        load_novelty_artifacts([bad])
