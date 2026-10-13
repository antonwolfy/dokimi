# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Named cost tiers, and the validity each one gives up to be cheap.

Instrumented over three real skills with a counting client, the measurement is
``~4 model calls per paired probe`` -- answering and grading are each half the bill on a
corpus whose atoms the retention oracle resolves locally. They are not the whole bill
everywhere: the oracle escalates the ambiguous band to a model, once per atom for carrier
confirmation and once per atom per shortening candidate, and on a corpus that escalates
heavily that term measured 35% of the total. A full-tier run of a 1,700-word skill came to 1,078
calls; the same skill at a triage budget came to 103. So the cost lever is the **probe
budget**, not the stage switches, and a tier is mostly a statement about atoms and probe
kinds.

The reason tiers live here rather than in a wiki: a cheap run that does not say what it
gave up gets quoted as if it were a sweep. Every tier carries ``forfeits`` -- the claims a
run at that tier may not make -- and those strings are written into ``run_config.tier``
and into the artifact's warnings, so the ceiling travels with the number.
"""

from __future__ import annotations

#: What a run gives up, keyed by the setting that is off ("sampled": an atom cap the
#: artifact reached). The forfeits of a run are derived from its resolved settings and,
#: once known, its atom count -- not fixed per tier -- so `--no-verify` adds the
#: faithfulness forfeit, and `--all-atoms` or an atom set under the cap drops the
#: sampled-rate ones.
FORFEITS: dict[str, list[str]] = {
    "sampled": [
        "`added` is a sampled rate over the atom cap: usable as a sign, not as a figure, "
        "and not comparable with another artifact's; pass --all-atoms for the full sweep",
        "`frac_carrying_nothing` is not interpretable on a capped atom set (0.064 read "
        "as 0.743 on the study's largest artifact)",
    ],
    "verify_faithfulness": [
        "atoms are not checked against the spans they were extracted from, so "
        "`faithfulness` is empty and distortion is unbounded",
    ],
    "shorten_artifact": [
        "no shortening candidates are scored, so nothing here says what could be cut",
    ],
    "paraphrases": [
        "no paraphrase probe, so a `redundant` verdict is unprotected against the model "
        "matching the artifact's own wording",
    ],
    "reversals": ["no reversal probe, so planted-inversion resistance is unmeasured"],
    "confirm_carriers": [
        "atoms are not checked against the spans cited for them, so no span colour is "
        "confirmed",
    ],
    "classify_content": [
        "content categories are not judged, so `harmful_conflicting` is unmeasured -- "
        "the one category that can make an artifact worse than nothing",
    ],
}


def forfeits(settings: dict, *, n_atoms: int | None = None) -> list[str]:
    """The claims a run with these settings may not make.

    Args:
        settings: Resolved ``AnalyzeConfig`` fields; a stage switch that is absent is off.
        n_atoms: Atoms extracted, when known. Before extraction a cap is assumed reached.
    """
    cap = settings.get("max_atoms")
    capped = cap is not None and (n_atoms is None or n_atoms >= cap)
    out = list(FORFEITS["sampled"]) if capped else []
    if capped and settings.get("shorten_artifact"):
        out.append(
            "shortening candidates are scored only against the capped atoms, i.e. the "
            "opening of the artifact: a cut of the uncovered tail looks free"
        )
    for setting, lines in FORFEITS.items():
        if setting != "sampled" and not settings.get(setting):
            out.extend(lines)
    return out


#: Tier -> (settings, forfeited claims at those settings).
TIERS: dict[str, dict] = {
    "triage": {"settings": {
        "max_atoms": 25, "paraphrases": 0, "reversals": False,
        "verify_faithfulness": False, "classify_content": False,
        "shorten_artifact": False, "confirm_carriers": False,
    }},
    "standard": {"settings": {
        "max_atoms": 60, "paraphrases": 1, "reversals": False,
        "verify_faithfulness": True, "classify_content": False,
        "shorten_artifact": True, "confirm_carriers": True,
    }},
    "study": {"settings": {
        "max_atoms": 120, "paraphrases": 1, "reversals": True,
        "verify_faithfulness": True, "classify_content": True,
        "shorten_artifact": True, "confirm_carriers": True,
    }},
}
for _spec in TIERS.values():
    _spec["forfeits"] = forfeits(_spec["settings"])

#: The atom cap when neither a tier nor `--max-atoms` says otherwise. The CLI default is
#: `None` (unset) so an explicit `--max-atoms 120` is distinguishable from silence; without
#: that sentinel a user who typed the old default would have had it silently replaced by
#: the tier's.
DEFAULT_MAX_ATOMS = 120

#: The CLI defaults for every tier-controlled flag. A flag whose parsed value differs from
#: its default was set by the user and wins over the tier; ``tests/test_novelty_tiers.py``
#: asserts this table against the parser, so the two cannot drift apart.
FLAG_DEFAULTS: dict[str, object] = {
    "max_atoms": None,
    # After max_atoms on purpose: as without a tier, --all-atoms beats --max-atoms.
    "all_atoms": False,
    "no_paraphrase": False,
    "no_reversal": False,
    "no_verify": False,
    "no_classify": False,
    "no_shorten": False,
    "no_confirm_carriers": False,
}

#: Which ``AnalyzeConfig`` field each flag decides, and whether the flag negates it.
_FLAG_TO_SETTING: dict[str, tuple[str, bool]] = {
    "max_atoms": ("max_atoms", False),
    "all_atoms": ("max_atoms", False),
    "no_paraphrase": ("paraphrases", True),
    "no_reversal": ("reversals", True),
    "no_verify": ("verify_faithfulness", True),
    "no_classify": ("classify_content", True),
    "no_shorten": ("shorten_artifact", True),
    "no_confirm_carriers": ("confirm_carriers", True),
}


def resolve(tier: str | None, flags: dict) -> dict:
    """Merge a tier with the flags the user actually set.

    An explicit flag always wins over the tier -- a tier is a starting point, not a lock --
    and the override is recorded so the result cannot be read as a stock tier run.

    Args:
        tier: Tier name, or ``None`` for the historical defaults.
        flags: Parsed flag values, keyed as in :data:`FLAG_DEFAULTS`.

    Returns:
        ``{"settings": {...}, "tier": {...}}``. ``settings`` are ``AnalyzeConfig`` fields to
        apply; ``tier`` is the record for ``run_config`` (name, forfeits, overrides).

    Raises:
        KeyError: Unknown tier name.
    """
    if tier is None:
        return {"settings": {}, "tier": {}}
    spec = TIERS[tier]
    settings = dict(spec["settings"])
    overrides: dict[str, object] = {}
    # Explicit order, not caller insertion order: `--all-atoms` beats `--max-atoms` exactly
    # as it does without a tier, and that precedence must not depend on how the caller
    # happened to build the dict.
    ordered = sorted(flags.items(), key=lambda pair: list(FLAG_DEFAULTS).index(pair[0])
                     if pair[0] in FLAG_DEFAULTS else len(FLAG_DEFAULTS))
    for flag, value in ordered:
        if flag not in _FLAG_TO_SETTING or value == FLAG_DEFAULTS[flag]:
            continue
        if flag == "max_atoms" and flags.get("all_atoms"):
            continue  # discarded by --all-atoms, so not a setting this run applied
        field, negates = _FLAG_TO_SETTING[flag]
        resolved: object = (not value) if negates else value
        if field == "paraphrases":
            resolved = 0 if value else 1
        if flag == "all_atoms":
            resolved = None  # no cap: the full sweep the `study` forfeit points to
        if settings.get(field) != resolved:
            overrides[flag] = value
        settings[field] = resolved
    return {
        "settings": settings,
        "tier": {
            "name": tier,
            "forfeits": forfeits(settings),
            "overrides": overrides,
        },
    }


def estimate_calls(n_atoms: int, settings: dict, *, n_arms: int = 2) -> dict:
    """Project the model-call bill before spending it.

    From the instrumented runs: every probe, reversal included, costs an answer and a grade
    in each arm, and that product is the whole bill to within a few percent. The per-batch
    stages (extraction, wording generation, the need graph, classification) and the
    per-atom faithfulness check add tens of calls, not thousands. Validated against a
    counting client over three real skills at all three tiers: the projection came within
    1-3% of the counted total at every point (see the PR that introduced tiers).

    Args:
        n_atoms: Atoms expected after the cap.
        settings: Resolved tier settings (``paraphrases``, ``reversals``, stage switches).
        n_arms: Arms in the run, including the baseline.

    Returns:
        ``{"n_atoms", "paired_probes", "reversal_probes", "probe_calls", "stage_calls",
        "oracle_pairs", "total_calls", "total_calls_if_every_pair_escalates"}``.
        ``total_calls`` assumes the retention oracle resolves every pair locally, which is
        what the validated 1-3% figure was measured on; the second total is the other end
        of the range. The real figure also moves with batch sizes and retries.
    """
    paired = n_atoms * (1 + (1 if settings.get("paraphrases") else 0))
    reversals = n_atoms if settings.get("reversals") else 0
    budgets = len(settings.get("budgets") or ()) or 2
    strategies = settings.get("shortening_strategies", 4)
    # Reversals are graded in every arm too: the baseline arm's resistance to a planted
    # inversion is a reported control, not a by-product.
    probe_calls = (paired + reversals) * n_arms * 2
    stage_calls = (
        max(1, round(n_atoms / 12))                                # extraction batches
        + (n_atoms if settings.get("verify_faithfulness") else 0)   # one per atom
        + (1 if settings.get("paraphrases") else 0)
        + (1 if settings.get("reversals") else 0)
        + 1                                                        # the need graph
        + (2 if settings.get("classify_content") else 0)
    )
    # The retention oracle resolves most pairs locally (retrieval then NLI) and escalates
    # only the ambiguous band, so its cost is a range, not a number: zero when nothing
    # escalates, one call per checked pair when everything does. Both ends are reported
    # because a corpus that escalates heavily measured 1.4-1.6x the no-escalation total.
    oracle_pairs = (
        (n_atoms if settings.get("confirm_carriers") else 0)
        + (n_atoms * budgets * strategies if settings.get("shorten_artifact") else 0)
    )
    return {
        "n_atoms": n_atoms,
        "paired_probes": paired,
        "reversal_probes": reversals,
        "probe_calls": probe_calls,
        "stage_calls": stage_calls,
        "oracle_pairs": oracle_pairs,
        "total_calls": probe_calls + stage_calls,
        "total_calls_if_every_pair_escalates": probe_calls + stage_calls + oracle_pairs,
    }
