# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Wire the novelty stages into one analysis of one artifact against one model.

Stage order is a dependency order, not a preference: the need graph must exist before
value can be judged (relevance comes from outside the artifact), and the paired probes
must exist before categories can use the measured known/new axis instead of asking a
model what it knew.

Every stage is skippable, because cost is real — the measurement is
``atoms × probes × arms × (answer + grade)`` — and a cheap run that says what it skipped
is more useful than an expensive run nobody starts. Each skip appends a warning to the
artifact so a partial run is never quoted as a full sweep.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from . import atoms as atoms_mod
from . import attribute, classify, measure, needs, probes, report, retention, shorten, spans
from .client import LLMClient, roll_up_cost
from .retention import RetentionOracle


@dataclass
class AnalyzeConfig:
    """What to run and how much of it."""

    artifact_ref: str
    artifact_kind: str = "skill"
    name: str = ""
    description: str = ""
    frontmatter: str = ""
    max_atoms: int | None = 120
    paraphrases: int = 1
    reversals: bool = True
    arms: tuple[str, ...] = (measure.BASELINE_ARM, "full")
    budgets: tuple[float, ...] = (0.75, 0.5)
    concurrency: int = 5
    allow_self_judge: bool = False
    verify_faithfulness: bool = True
    classify_content: bool = True
    shorten_artifact: bool = True
    # Check each atom against the span the extractor cited for it. Cheap (one cached oracle
    # verdict per cited pair, mostly resolved lexically) and it decides whether the span
    # views may assert a colour: 0.19 of atoms in the study were unrecoverable from their
    # cited file, so a run that skips this must not present attribution as confirmed.
    confirm_carriers: bool = True
    placebo_text: str | None = None
    cache_dir: Path | None = None
    seed: int = 0


def _prompts_sha256() -> str:
    """Digest of every stage prompt, so a prompt edit is visible as a different measurement."""
    mods = (atoms_mod, classify, measure, needs, probes, retention)
    texts = sorted(v for m in mods for k, v in vars(m).items()
                   if k.endswith(("_PROMPT", "_SYSTEM")) and isinstance(v, str))
    return "sha256:" + hashlib.sha256("\0".join(texts).encode("utf-8")).hexdigest()


def _run_config(config: "AnalyzeConfig") -> dict:
    """What decided this cell's numbers beyond the models: two cells compare only if these match."""
    return {
        "seed": config.seed,
        "max_atoms": config.max_atoms,
        "paraphrases": config.paraphrases,
        "reversals": config.reversals,
        "arms": list(config.arms),
        "budgets": list(config.budgets),
        "stages": {
            "verify": config.verify_faithfulness, "classify": config.classify_content,
            "shorten": config.shorten_artifact, "confirm_carriers": config.confirm_carriers,
        },
        "prompts_sha256": _prompts_sha256(),
    }


@dataclass
class AnalyzeResult:
    """Everything one analysis produced, plus the renderable views."""

    artifact: dict
    attributions: list = field(default_factory=list)
    candidates: list = field(default_factory=list)
    atoms: list = field(default_factory=list)
    spans: list = field(default_factory=list)
    measure_result: object | None = None


def analyze(
    text: str,
    config: AnalyzeConfig,
    *,
    extractor: LLMClient,
    answerer: LLMClient,
    judge: LLMClient,
    ref_digest: str | None = None,
) -> AnalyzeResult:
    """Run the full pipeline over one artifact's text.

    Args:
        text: The artifact body (frontmatter already split off into ``config``).
        config: What to run.
        extractor: Builds atoms, probe wordings, the need graph, and the value verdicts.
        answerer: The model under measurement.
        judge: Grades responses; must differ from ``answerer`` unless allowed.
        ref_digest: Content digest of the artifact, so a stored result can be tied to the
            exact bytes it was measured on.
    """
    warnings: list[str] = []
    span_list = spans.segment(text)
    atom_list = atoms_mod.extract_atoms(
        span_list, client=extractor, cap=config.max_atoms
    )
    sampling = (
        f"cap-per-artifact:{config.max_atoms}" if config.max_atoms is not None else "full"
    )
    if config.max_atoms is not None and len(atom_list) >= config.max_atoms:
        warnings.append(
            f"atom extraction hit the cap of {config.max_atoms}; rates describe the "
            "sampled atoms, not the whole artifact"
        )
    if not atom_list:
        warnings.append("no atoms with span provenance were extracted; nothing to measure")

    faithfulness = None
    if config.verify_faithfulness and atom_list:
        faithfulness = atoms_mod.verify_atoms(atom_list, span_list, client=extractor)
        distorted = faithfulness.get("distorted", 0) + faithfulness.get("unsupported", 0)
        if distorted:
            warnings.append(
                f"{distorted} atoms are distorted or unsupported by their own spans; they "
                "stay in the set and are visible in atoms.faithfulness"
            )

    graph = needs.build_need_graph(
        config.name or config.artifact_ref, config.description, client=extractor
    )
    if not graph.nodes:
        warnings.append(
            "the need graph is empty, so relevance fell back to a flat weight; `value` and "
            "out-of-scope detection are not meaningful for this run"
        )
    relevance = needs.match_atoms(atom_list, graph)

    probe_list = probes.build_probes(
        atom_list, client=extractor,
        paraphrases=config.paraphrases, reversals=config.reversals,
    )
    measure_result = measure.run_measurement(
        atom_list, probe_list, text,
        answerer=answerer, judge=judge, arms=config.arms,
        concurrency=config.concurrency, allow_self_judge=config.allow_self_judge,
        placebo_text=config.placebo_text, seed=config.seed,
    )
    if config.allow_self_judge and judge.model == answerer.model:
        warnings.append(
            "judge and answerer are the same model (--allow-self-judge): scores are inflated"
        )
    outcomes = measure.atom_outcomes(measure_result.runs, with_arm=measure_result.with_arm)
    # What *kind* of knowledge the model lacked, not just how much (skill-novelty-evidence.md
    # §10.1). The slices are the actionable cut for an author; the caveats ride along in the report.
    by_knowledge_kind = {
        scoring: measure.outcomes_by_atom_kind(
            measure_result.runs, atom_list,
            with_arm=measure_result.with_arm, scoring=scoring,
        )
        for scoring in ("lenient", "strict")
    }

    categories: dict[str, str] = {}
    conflicts: list[dict] = []
    if config.classify_content and atom_list:
        verdicts = classify.judge_value(
            atom_list, client=extractor, task=graph.task_statement()
        )
        conflicts = classify.detect_conflicts(atom_list, client=extractor)
        classify.apply_conflicts(verdicts, conflicts)
        categories = classify.categorize(atom_list, verdicts, outcomes)
    elif not config.classify_content:
        warnings.append("content categories were not judged (--no-classify)")

    attributions = attribute.attribute_spans(
        span_list, atom_list, outcomes=outcomes, categories=categories
    )
    oracle = RetentionOracle(client=extractor, cache_dir=config.cache_dir)
    confirmation: dict | None = None
    if config.confirm_carriers and atom_list:
        confirmation = attribute.carrier_confirmation(span_list, atom_list, oracle=oracle)
        if confirmation["n_unlocated"]:
            warnings.append(
                f"{confirmation['n_unlocated']} of {confirmation['n_atoms']} atoms were not "
                "recoverable from any span cited for them; they are reported as unlocated "
                "rather than attributed, and are not necessarily wrong (in the study the "
                "faithfulness check called 46 of 49 such atoms supported)"
            )
    elif not config.confirm_carriers:
        warnings.append(
            "span citations were not confirmed (--no-confirm-carriers): the span views "
            "report the extractor's citation as given"
        )
    candidates: list = []
    if config.shorten_artifact and atom_list:
        candidates = shorten.build_candidates(
            span_list, atom_list, oracle=oracle, budgets=config.budgets,
            relevance=relevance, outcomes=outcomes, categories=categories, seed=config.seed,
        )
        for candidate in candidates:
            candidate.text = shorten.render(
                span_list, candidate.kept_span_ids, frontmatter=config.frontmatter
            )
        unsafe = [c for c in candidates if not c.safe]
        if unsafe:
            warnings.append(
                f"{len(unsafe)} shortening candidates drop protected spans; they are reported "
                "so the knowledge-vs-protection gap is visible, not offered as accepted output"
            )

    payload = report.build_novelty_artifact(
        artifact_kind=config.artifact_kind,
        artifact_ref=config.artifact_ref,
        artifact_tokens=sum(s.tokens for s in span_list),
        ref_digest=ref_digest,
        model=answerer.model,
        provider=answerer.provider,
        judge_model=judge.model,
        atoms=atom_list,
        sampling=sampling,
        measure_result=measure_result,
        span_summary=spans.span_summary(span_list, atom_list, atom_cap=config.max_atoms),
        by_knowledge_kind=by_knowledge_kind,
        attribution_summary=attribute.attribution_summary(
            attributions, confirmation=confirmation
        ),
        categories=classify.category_counts(categories) if categories else {},
        faithfulness=faithfulness,
        graph_summary=graph.summary(),
        relevance=needs.relevance_summary(relevance),
        retention_stats=oracle.stats(),
        candidates=candidates,
        dead_weight=attribute.dead_weight(attributions),
        sole_carriers=attribute.sole_carriers(attributions),
        topics=attribute.topic_rollup(attributions),
        conflicts=conflicts,
        cost=roll_up_cost([extractor, answerer, judge]),
        warnings=warnings,
    )
    payload["run_config"] = _run_config(config)
    return AnalyzeResult(
        artifact=payload,
        attributions=attributions,
        candidates=candidates,
        atoms=atom_list,
        spans=span_list,
        measure_result=measure_result,
    )


def load_artifact_text(ref: str) -> tuple[str, str, str, str, str]:
    """Resolve an artifact reference to ``(kind, name, description, frontmatter, body)``.

    Supported today: ``skill:<path>`` (a ``SKILL.md`` or its directory) and
    ``text:<path>`` for any other context artifact. A plain path is treated as text, and
    a text artifact has no description — which means its need graph, and therefore its
    relevance weighting, is weaker. The analyzer says so in a warning rather than
    pretending the two cases are equivalent.
    """
    if ref.startswith("skill:"):
        from agent_benchmarks.skills.loader import load_skill

        skill = load_skill(ref.removeprefix("skill:"))
        # Verbatim, as shorten.render promises: a rebuilt `description: a: b` is not YAML.
        lines = skill.path.read_text(encoding="utf-8").lstrip("﻿").splitlines()
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
        frontmatter = "\n".join(lines[: end + 1])
        return "skill", skill.name, skill.description, frontmatter, skill.body
    path = Path(ref.removeprefix("text:"))
    if not path.is_file():
        raise FileNotFoundError(f"artifact not found: {path}")
    return "text", path.stem, "", "", path.read_text(encoding="utf-8")
