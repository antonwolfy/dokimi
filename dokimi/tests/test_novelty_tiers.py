# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Cost tiers: what each one gives up, who wins over whom, and the call projection."""

from __future__ import annotations

import json

import pytest

from dokimi.cli import build_parser
from dokimi.novelty.tiers import (
    FLAG_DEFAULTS,
    FORFEITS,
    TIERS,
    estimate_calls,
    resolve,
)


def _parse(*argv):
    return build_parser().parse_args(list(argv))


def _flags(args):
    return {flag: getattr(args, flag) for flag in FLAG_DEFAULTS}


def test_the_recorded_flag_defaults_match_the_parser():
    """If a CLI default moves, the override detection silently breaks — fail here instead."""
    parsed = _parse("novelty", "analyze", "--artifact", "skill:x")
    for flag, default in FLAG_DEFAULTS.items():
        assert getattr(parsed, flag) == default, flag


def test_no_tier_leaves_the_historical_defaults_alone():
    resolved = resolve(None, _flags(_parse("novelty", "analyze", "--artifact", "skill:x")))
    assert resolved == {"settings": {}, "tier": {}}


def test_every_tier_names_what_it_forfeits():
    for name, spec in TIERS.items():
        assert spec["forfeits"], name
        resolved = resolve(name, _flags(_parse("novelty", "analyze", "--artifact", "skill:x")))
        assert resolved["tier"]["name"] == name
        assert resolved["tier"]["forfeits"] == spec["forfeits"]
        assert resolved["tier"]["overrides"] == {}


def test_a_cheap_tier_buys_its_saving_from_the_probe_budget():
    triage = resolve("triage", _flags(_parse("novelty", "analyze", "--artifact", "skill:x")))
    study = resolve("study", _flags(_parse("novelty", "analyze", "--artifact", "skill:x")))
    assert triage["settings"]["max_atoms"] < study["settings"]["max_atoms"]
    assert (triage["settings"]["paraphrases"], triage["settings"]["reversals"]) == (0, False)
    assert (study["settings"]["paraphrases"], study["settings"]["reversals"]) == (1, True)
    # The measured shape: triage is ~10x cheaper than study on the same artifact.
    cheap = estimate_calls(25, triage["settings"])["total_calls"]
    full = estimate_calls(120, study["settings"])["total_calls"]
    assert full / cheap > 8


def test_an_explicit_flag_wins_over_the_tier_and_is_recorded():
    args = _parse("novelty", "analyze", "--artifact", "skill:x", "--tier", "triage",
                  "--max-atoms", "90")
    resolved = resolve(args.tier, _flags(args))
    assert resolved["settings"]["max_atoms"] == 90
    assert resolved["tier"]["overrides"] == {"max_atoms": 90}


def test_all_atoms_lifts_the_tier_cap_as_its_forfeit_says():
    # The `study` forfeit tells the reader to pass --all-atoms for the full sweep.
    args = _parse("novelty", "analyze", "--artifact", "skill:x", "--tier", "study",
                  "--all-atoms")
    resolved = resolve(args.tier, _flags(args))
    assert resolved["settings"]["max_atoms"] is None
    assert resolved["tier"]["overrides"] == {"all_atoms": True}


def test_a_flag_that_agrees_with_the_tier_is_not_recorded_as_an_override():
    args = _parse("novelty", "analyze", "--artifact", "skill:x", "--tier", "triage",
                  "--no-reversal")
    resolved = resolve(args.tier, _flags(args))
    assert resolved["settings"]["reversals"] is False
    assert resolved["tier"]["overrides"] == {}


def test_turning_a_stage_back_on_is_not_expressible_so_the_tier_keeps_it_off():
    # The flags are all negations; there is no `--classify`, so a tier that drops a stage
    # can only be overridden towards *less*. The resolution must not invent the other way.
    args = _parse("novelty", "analyze", "--artifact", "skill:x", "--tier", "triage")
    assert resolve(args.tier, _flags(args))["settings"]["classify_content"] is False


def test_the_projection_counts_every_probe_in_every_arm():
    settings = {"paraphrases": 1, "reversals": True, "verify_faithfulness": True,
                "classify_content": True, "confirm_carriers": True}
    estimate = estimate_calls(81, settings, n_arms=2)
    assert estimate["paired_probes"] == 162          # direct + paraphrase
    assert estimate["reversal_probes"] == 81
    # answer + grade, per arm, for paired and reversal probes alike
    assert estimate["probe_calls"] == (162 + 81) * 2 * 2
    # Counted against a real run of the same artifact: 1,078 calls measured.
    assert 1040 <= estimate["total_calls"] <= 1120


def test_dropping_probe_kinds_is_what_makes_a_run_cheap():
    direct_only = estimate_calls(81, {"paraphrases": 0, "reversals": False})
    everything = estimate_calls(81, {"paraphrases": 1, "reversals": True})
    assert everything["probe_calls"] == 3 * direct_only["probe_calls"]


def test_estimate_only_spends_nothing_and_prints_the_bill(tmp_path, capsys):
    root = tmp_path / "s"
    root.mkdir()
    (root / "SKILL.md").write_text(
        "---\nname: s\ndescription: d\n---\n\n# S\n\nUse `--accel` on driver 2.1.\n"
        "Do not use it on 1.0.\n", encoding="utf-8")
    args = _parse("novelty", "analyze", "--artifact", f"skill:{root}",
                  "--tier", "study", "--estimate-only")
    args.func(args)                       # no client is constructed, no network touched
    out = capsys.readouterr()
    payload = json.loads(out.out)
    assert payload["estimate"]["total_calls"] > 0
    assert payload["tier"]["name"] == "study"
    assert "nothing was measured" in out.err


def test_an_unknown_tier_is_refused_by_the_parser():
    with pytest.raises(SystemExit):
        _parse("novelty", "analyze", "--artifact", "skill:x", "--tier", "cheap")


def test_passing_the_default_atom_cap_explicitly_still_beats_the_tier():
    # The sweep case: `--tier triage --max-atoms 120` used to be indistinguishable from
    # `--tier triage`, so the user's number was silently replaced by 25.
    args = _parse("novelty", "analyze", "--artifact", "skill:x", "--tier", "triage",
                  "--max-atoms", "120")
    resolved = resolve(args.tier, _flags(args))
    assert resolved["settings"]["max_atoms"] == 120
    assert resolved["tier"]["overrides"] == {"max_atoms": 120}


def test_an_unset_cap_resolves_to_the_documented_default():
    from dokimi.commands import novelty as novelty_cmd
    from dokimi.novelty.tiers import DEFAULT_MAX_ATOMS

    args = _parse("novelty", "analyze", "--artifact", "skill:x")
    assert args.max_atoms is None                       # the sentinel, not 120
    assert novelty_cmd._atom_cap(args) == DEFAULT_MAX_ATOMS
    assert resolve(None, _flags(args)) == {"settings": {}, "tier": {}}


def test_every_dropped_stage_appears_in_the_tier_s_forfeits():
    for name, spec in TIERS.items():
        forfeits = " ".join(spec["forfeits"]).lower()
        settings = spec["settings"]
        if not settings.get("shorten_artifact"):
            assert "shortening" in forfeits, name
        if not settings.get("classify_content"):
            assert "categor" in forfeits or "harmful" in forfeits, name
        if not settings.get("confirm_carriers"):
            assert "cited" in forfeits or "span colour" in forfeits, name
        if not settings.get("reversals"):
            assert "reversal" in forfeits, name
        if not settings.get("paraphrases"):
            assert "paraphrase" in forfeits, name


def test_the_projection_reports_the_oracle_as_a_range_not_as_zero():
    settings = dict(TIERS["study"]["settings"], budgets=(0.75, 0.5))
    estimate = estimate_calls(81, settings)
    # The retention oracle escalates only its ambiguous band, so its cost is between zero
    # and one call per checked pair. Reporting only the lower end made the published
    # 1-3% accuracy claim hold for corpora that never escalate and nothing else.
    assert estimate["oracle_pairs"] > 0
    assert estimate["total_calls_if_every_pair_escalates"] > estimate["total_calls"]
    # A tier that scores no shortening candidates and confirms no carriers has no oracle.
    assert estimate_calls(25, TIERS["triage"]["settings"])["oracle_pairs"] == 0


def test_the_atom_cap_default_is_one_value_in_two_places():
    from dokimi.novelty.analyze import AnalyzeConfig
    from dokimi.novelty.tiers import DEFAULT_MAX_ATOMS

    # The sentinel only works if the CLI's resolved default and the library default agree.
    assert AnalyzeConfig(artifact_ref="x").max_atoms == DEFAULT_MAX_ATOMS


def test_flag_precedence_does_not_depend_on_dict_order():
    both = {"all_atoms": True, "max_atoms": 50}
    assert resolve("study", both)["settings"]["max_atoms"] is None
    assert resolve("study", dict(reversed(list(both.items()))))["settings"]["max_atoms"] is None


def test_the_faithfulness_check_is_named_where_a_tier_drops_it():
    for name, spec in TIERS.items():
        if not spec["settings"].get("verify_faithfulness"):
            forfeits = " ".join(spec["forfeits"]).lower()
            assert "faithfulness" in forfeits or "distortion" in forfeits, name


def test_forfeits_follow_the_resolved_settings():
    from dokimi.novelty.tiers import forfeits

    sampled = FORFEITS["sampled"][0]
    standard = TIERS["standard"]["settings"]
    # Before extraction the cap is assumed reached; an atom set under it is not sampled.
    assert sampled in forfeits(standard)
    assert sampled not in forfeits(standard, n_atoms=15)
    assert sampled in forfeits(standard, n_atoms=60)
    # --all-atoms drops the sampled-rate forfeit, triage included.
    args = _parse("novelty", "analyze", "--artifact", "skill:x", "--tier", "triage",
                  "--all-atoms")
    assert sampled not in resolve(args.tier, _flags(args))["tier"]["forfeits"]
    # --no-verify adds the faithfulness forfeit the tier did not have.
    args = _parse("novelty", "analyze", "--artifact", "skill:x", "--tier", "standard",
                  "--no-verify")
    assert FORFEITS["verify_faithfulness"][0] in resolve(args.tier, _flags(args))["tier"][
        "forfeits"]
    assert FORFEITS["verify_faithfulness"][0] not in TIERS["standard"]["forfeits"]


def test_all_atoms_does_not_record_max_atoms_override():
    args = _parse("novelty", "analyze", "--artifact", "skill:x", "--tier", "triage",
                  "--max-atoms", "10", "--all-atoms")
    resolved = resolve(args.tier, _flags(args))
    assert resolved["settings"]["max_atoms"] is None
    assert resolved["tier"]["overrides"] == {"all_atoms": True}


def test_a_run_without_wordings_is_not_reported_as_having_clean_wordings():
    from dokimi.gate.novelty_gate import evaluate_novelty

    from tests.test_novelty_gate import _artifact

    empty = {"n_probes": 16, "by_kind": {}, "malformed_rate": 0.0}
    verdict = evaluate_novelty(_artifact(probes=empty))
    row = next(c for c in verdict.checks if c.name == "probe_wording_fidelity")
    assert row.measured is False
    assert "probe_wording_fidelity" in verdict.not_measured
    # An aggregate that quotes a high rate with no per-kind rows still fails.
    bad = evaluate_novelty(_artifact(probes=dict(empty, malformed_rate=0.9)))
    assert next(c for c in bad.checks if c.name == "probe_wording_fidelity").passed is False


def test_flags_that_drop_the_probe_kinds_warn_without_a_tier(tmp_path):
    from tests.test_novelty_analyze import _analyze

    warnings = _analyze(tmp_path, paraphrases=0, reversals=False).artifact["warnings"]
    assert any("no paraphrase probe" in w for w in warnings)
    assert any("no reversal probe" in w for w in warnings)
    full = _analyze(tmp_path / "f").artifact["warnings"]
    assert not any("no paraphrase probe" in w or "no reversal probe" in w for w in full)


def test_shortening_under_a_reached_cap_says_it_saw_only_the_opening():
    from dokimi.novelty.tiers import forfeits

    on = {"max_atoms": 60, "shorten_artifact": True, "paraphrases": 1, "reversals": True,
          "verify_faithfulness": True, "classify_content": True, "confirm_carriers": True}
    assert any("opening of the artifact" in f for f in forfeits(on, n_atoms=60))
    assert not any("opening of the artifact" in f for f in forfeits(on, n_atoms=10))
    assert not any("opening of the artifact" in f for f in forfeits(dict(on, max_atoms=None)))
    assert not any("opening of the artifact" in f
                   for f in forfeits(dict(on, shorten_artifact=False), n_atoms=60))
