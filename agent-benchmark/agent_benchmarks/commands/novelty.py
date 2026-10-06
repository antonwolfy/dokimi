# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""novelty subcommand group: what does this artifact add to this model?

Standalone by design. `novelty analyze` needs an artifact and a model — no question set,
no task suite, no benchmark run — because the first user is an author editing a skill,
not a CI job. The pieces (`atoms`, `probe`, `shorten`, `view`) exist so an expensive
stage can be paid for once and reused.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROVIDERS = ["openai", "anthropic", "amazon-bedrock", "google-vertex", "openrouter", "openai-codex"]


def cmd_novelty_analyze(args: argparse.Namespace) -> None:
    """Run the full pipeline over one artifact and write the novelty artifact + views."""
    from agent_benchmarks.artifacts import save_artifact
    # Import the symbols, not the module: the package re-exports `analyze` as the
    # function, which shadows the submodule of the same name.
    from agent_benchmarks.novelty.analyze import AnalyzeConfig, analyze, load_artifact_text
    from agent_benchmarks.novelty.atoms import ExtractionError
    from agent_benchmarks.novelty.measure import SelfJudgeError
    from agent_benchmarks.novelty.report import (
        render_annotated_html,
        render_annotated_markdown,
        render_novelty_markdown,
    )

    try:
        kind, name, description, frontmatter, body = load_artifact_text(args.artifact)
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(f"cannot load --artifact {args.artifact}: {exc}") from None

    extractor, answerer, judge = _clients(args)
    config = AnalyzeConfig(
        artifact_ref=args.artifact,
        artifact_kind=kind,
        name=name,
        description=description,
        frontmatter=frontmatter,
        max_atoms=None if args.all_atoms else args.max_atoms,
        paraphrases=0 if args.no_paraphrase else 1,
        reversals=not args.no_reversal,
        arms=tuple(_arms(args.arms)),
        budgets=tuple(args.budgets),
        concurrency=args.concurrency,
        allow_self_judge=args.allow_self_judge,
        verify_faithfulness=not args.no_verify,
        classify_content=not args.no_classify,
        shorten_artifact=not args.no_shorten,
        confirm_carriers=not args.no_confirm_carriers,
        placebo_text=(
            Path(args.placebo_text).read_text(encoding="utf-8")
            if args.placebo_text else None
        ),
        cache_dir=Path(args.cache_dir) if args.cache_dir else None,
        seed=args.seed,
    )
    try:
        result = analyze(
            body, config,
            extractor=extractor, answerer=answerer, judge=judge,
            ref_digest=_digest(args.artifact),
        )
    except (SelfJudgeError, ExtractionError) as exc:
        raise SystemExit(str(exc)) from None

    out_dir = Path(args.out_dir) if args.out_dir else _default_dir(args.artifact)
    out_json = Path(args.out_json) if args.out_json else out_dir / "novelty.json"
    save_artifact("novelty", result.artifact, out_json)
    out_md = out_json.with_suffix(".md")
    out_md.write_text(render_novelty_markdown(result.artifact), encoding="utf-8")
    title = f"{name or args.artifact} × {answerer.model}"
    view_path = out_dir / ("annotated.html" if args.view_format == "html" else "annotated.md")
    render = render_annotated_html if args.view_format == "html" else render_annotated_markdown
    view_path.parent.mkdir(parents=True, exist_ok=True)
    view_path.write_text(render(result.attributions, title=title), encoding="utf-8")

    print(f"OK Saved novelty artifact: {out_json}")
    print(f"OK Saved novelty report:   {out_md}")
    print(f"OK Saved annotated view:   {view_path}")
    _print_headline(result.artifact)


def cmd_novelty_atoms(args: argparse.Namespace) -> None:
    """Extract atoms and spans only — the expensive stage, cached for reuse."""
    from agent_benchmarks.novelty.analyze import load_artifact_text
    from agent_benchmarks.novelty.atoms import (
        ExtractionError,
        extract_atoms,
        save_atoms,
        verify_atoms,
    )
    from agent_benchmarks.novelty.spans import segment, span_summary

    _kind, _name, _description, _frontmatter, body = load_artifact_text(args.artifact)
    extractor = _client(args.extract_model or args.model, args.provider, "extractor", args)
    spans = segment(body)
    cap = None if args.all_atoms else args.max_atoms
    try:
        atoms = extract_atoms(spans, client=extractor, cap=cap)
    except ExtractionError as exc:
        raise SystemExit(str(exc)) from None
    if not args.no_verify:
        verify_atoms(atoms, spans, client=extractor)
    out = Path(args.out) if args.out else _default_dir(args.artifact) / "atoms.json"
    save_atoms(atoms, spans, out, extractor=extractor.model, cap=cap)
    print(f"OK Saved {len(atoms)} atoms over {len(spans)} spans: {out}")
    print(json.dumps(span_summary(spans, atoms), indent=2))


def cmd_novelty_probe(args: argparse.Namespace) -> None:
    """Run the paired probes against a saved atom set and print the 2×2."""
    from agent_benchmarks.novelty.analyze import load_artifact_text
    from agent_benchmarks.novelty.atoms import load_atoms
    from agent_benchmarks.novelty.measure import SelfJudgeError, run_measurement
    from agent_benchmarks.novelty.probes import build_probe_set

    atoms, _spans = load_atoms(args.atoms)
    _kind, _name, _description, _frontmatter, body = load_artifact_text(args.artifact)
    extractor, answerer, judge = _clients(args)
    if json.loads(Path(args.atoms).read_text(encoding="utf-8")).get("extractor") == answerer.model:
        print(f"WARNING: {answerer.model} extracted these atoms, so the model under measurement "
              "wrote its own answer key; extract with a different --extract-model",
              file=sys.stderr)
    probe_set = build_probe_set(
        atoms, client=None if args.no_paraphrase and args.no_reversal else extractor,
        paraphrases=0 if args.no_paraphrase else 1, reversals=not args.no_reversal,
    )
    probes = probe_set.probes
    for kind, row in sorted(probe_set.fidelity.items()):
        if row["rejected"]:
            print(f"WARNING: dropped {row['rejected']} of {row['generated']} generated {kind} "
                  f"wordings that failed the fidelity check "
                  f"({', '.join(f'{r}={n}' for r, n in sorted(row['reasons'].items()))})",
                  file=sys.stderr)
    try:
        result = run_measurement(
            atoms, probes, body, answerer=answerer, judge=judge,
            arms=tuple(_arms(args.arms)), concurrency=args.concurrency,
            allow_self_judge=args.allow_self_judge, seed=args.seed,
            placebo_text=(
                Path(args.placebo_text).read_text(encoding="utf-8") if args.placebo_text else None
            ),
        )
    except (SelfJudgeError, ValueError) as exc:
        raise SystemExit(str(exc)) from None

    payload = {
        "artifact": args.artifact,
        "model": answerer.model,
        "judge_model": judge.model,
        "probes": probe_set.as_dict(),
        "paired": {scoring: result.paired(scoring) for scoring in ("lenient", "strict")},
        "arms": {scoring: result.arm_means(scoring) for scoring in ("lenient", "strict")},
        "abstentions": result.abstentions(),
        "reversal_resisted": result.reversal_resisted(),
        "confidence_correlation": result.confidence_correlation(),
        "runs": [row.as_dict() for row in result.runs],
    }
    out = Path(args.out) if args.out else _default_dir(args.artifact) / "probes.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"OK Saved {len(result.runs)} probe runs: {out}")
    for scoring in ("lenient", "strict"):
        row = payload["paired"][scoring]
        print(
            f"{scoring:8s} added {row['added']}  already-knew {row['redundant']}  "
            f"degraded {row['degraded']}  still-missing {row['still_missing']}  "
            f"(n={row['n_paired']})"
        )


def cmd_novelty_shorten(args: argparse.Namespace) -> None:
    """Score shortening candidates on the five axes and optionally write the best one."""
    from agent_benchmarks.novelty.analyze import load_artifact_text
    from agent_benchmarks.novelty.atoms import load_atoms
    from agent_benchmarks.novelty.retention import RetentionOracle
    from agent_benchmarks.novelty.shorten import build_candidates, pick_best

    atoms, spans = load_atoms(args.atoms)
    _kind, _name, _description, frontmatter, _body = load_artifact_text(args.artifact)
    client = _client(args.extract_model or args.model, args.provider, "oracle", args) \
        if not args.lexical_only else None
    oracle = RetentionOracle(
        client=client, cache_dir=Path(args.cache_dir) if args.cache_dir else None
    )
    candidates = build_candidates(
        spans, atoms, oracle=oracle, budgets=tuple(args.budgets), seed=args.seed
    )
    print(
        f"{'strategy':20s} {'budget':>7s} {'tok':>6s} {'know':>6s} "
        f"{'value':>6s} {'prot':>6s} safe"
    )
    for candidate in candidates:
        row = candidate.as_dict()
        print(
            f"{row['strategy']:20s} {row['budget_frac']:7.2f} {row['token_frac']:6.2f} "
            f"{row['knowledge']:6.3f} {row['value']:6.3f} {row['protection']:6.3f} {row['safe']}"
        )
    if args.lexical_only:
        print(
            "NOTE lexical-only oracle: contradictions are invisible to it (0.00 measured "
            "contradiction recall), so `knowledge` here is a floor, not a verdict."
        )
    best = pick_best(candidates, require_safe=not args.allow_unsafe)
    if best is None:
        print("No candidate kept every protected span; the artifact's length is its content.")
        return
    print(
        f"Best safe candidate: {best.strategy} @ {best.budget_frac} → {best.token_frac} tokens, "
        f"knowledge {best.knowledge}, protection {best.protection}"
    )
    if args.out:
        from agent_benchmarks.novelty.shorten import render

        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(
            render(spans, best.kept_span_ids, frontmatter=frontmatter), encoding="utf-8"
        )
        print(f"OK Wrote candidate: {args.out}")


def cmd_novelty_view(args: argparse.Namespace) -> None:
    """Re-render the annotated view from a saved novelty artifact plus its atoms."""
    from agent_benchmarks.artifacts import load_artifact
    from agent_benchmarks.novelty.atoms import load_atoms
    from agent_benchmarks.novelty.attribute import attribute_spans
    from agent_benchmarks.novelty.report import render_annotated_html, render_annotated_markdown

    artifact = load_artifact("novelty", Path(args.novelty))
    atoms, spans = load_atoms(args.atoms)
    # Re-rendering needs per-atom outcomes; the artifact carries aggregates, so a view
    # rebuilt from it alone would colour by category only. Say so instead of implying the
    # colours mean more than they do.
    attributions = attribute_spans(spans, atoms)
    render = render_annotated_html if args.format == "html" else render_annotated_markdown
    title = f"{artifact['artifact']['ref']} × {artifact['model']}"
    out = Path(args.out) if args.out else Path(f"annotated.{args.format}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(attributions, title=title), encoding="utf-8")
    print(f"OK Saved annotated view: {out}")
    print(
        "NOTE colours here come from spans and categories only. For outcome colouring "
        "(added / degraded), render during `novelty analyze`, which has the paired runs."
    )


def register(sub, positive_int) -> None:
    """Add the `novelty` subcommand group."""
    novelty_p = sub.add_parser(
        "novelty",
        help="Measure what an artifact's content adds to a model",
    )
    novelty_sub = novelty_p.add_subparsers(dest="novelty_cmd", required=True)

    analyze_p = novelty_sub.add_parser(
        "analyze", help="Full pipeline: atoms → probes → categories → attribution → shortening"
    )
    _add_common(analyze_p, positive_int)
    _add_model_args(analyze_p, positive_int)
    analyze_p.add_argument("--out-dir", default=None, dest="out_dir")
    analyze_p.add_argument("--out-json", default=None, dest="out_json")
    analyze_p.add_argument("--view-format", default="html", choices=["html", "md"],
                           dest="view_format")
    analyze_p.add_argument("--no-classify", action="store_true", dest="no_classify",
                           help="Skip the judged content categories (cheaper; the artifact "
                                "records the skip as a warning)")
    analyze_p.add_argument("--no-shorten", action="store_true", dest="no_shorten")
    analyze_p.add_argument("--no-confirm-carriers", action="store_true",
                           dest="no_confirm_carriers",
                           help="Skip checking each atom against the span cited for it; the "
                                "span views then report the extractor's citation as given "
                                "(0.19 of atoms in the study were not recoverable from it)")
    analyze_p.add_argument("--no-verify", action="store_true", dest="no_verify",
                           help="Skip the per-atom faithfulness check")
    analyze_p.set_defaults(func=cmd_novelty_analyze)

    atoms_p = novelty_sub.add_parser("atoms", help="Extract knowledge atoms and spans only")
    _add_common(atoms_p, positive_int)
    atoms_p.add_argument("--model", default="gpt-4o-mini",
                         help="Extractor model when --extract-model is not given")
    atoms_p.add_argument("--extract-model", default=None, dest="extract_model")
    atoms_p.add_argument("--provider", default="openai", choices=PROVIDERS)
    atoms_p.add_argument("--max-tokens", type=positive_int, default=None, dest="max_tokens")
    atoms_p.add_argument("--no-verify", action="store_true", dest="no_verify")
    atoms_p.add_argument("--out", default=None)
    atoms_p.set_defaults(func=cmd_novelty_atoms)

    probe_p = novelty_sub.add_parser("probe", help="Run paired probes against a saved atom set")
    _add_common(probe_p, positive_int)
    _add_model_args(probe_p, positive_int)
    probe_p.add_argument("--atoms", required=True, help="atoms.json from `novelty atoms`")
    probe_p.add_argument("--out", default=None)
    probe_p.set_defaults(func=cmd_novelty_probe)

    shorten_p = novelty_sub.add_parser(
        "shorten", help="Score shortening candidates on tokens/knowledge/value/protection/routing"
    )
    _add_common(shorten_p, positive_int)
    shorten_p.add_argument("--atoms", required=True, help="atoms.json from `novelty atoms`")
    shorten_p.add_argument("--model", default="gpt-4o-mini", help="Retention adjudicator model")
    shorten_p.add_argument("--extract-model", default=None, dest="extract_model")
    shorten_p.add_argument("--provider", default="openai", choices=PROVIDERS)
    shorten_p.add_argument("--max-tokens", type=positive_int, default=None, dest="max_tokens")
    shorten_p.add_argument("--lexical-only", action="store_true", dest="lexical_only",
                           help="Run the retention oracle without an LLM adjudicator. Cheap and "
                                "reproducible, but blind to contradictions")
    shorten_p.add_argument("--allow-unsafe", action="store_true", dest="allow_unsafe",
                           help="Allow a best-candidate pick that drops protected spans")
    shorten_p.add_argument("--out", default=None, help="Write the chosen candidate here")
    shorten_p.set_defaults(func=cmd_novelty_shorten)

    view_p = novelty_sub.add_parser("view", help="Re-render the annotated artifact view")
    view_p.add_argument("--novelty", required=True, help="novelty.json from `novelty analyze`")
    view_p.add_argument("--atoms", required=True, help="atoms.json from `novelty atoms`")
    view_p.add_argument("--format", default="html", choices=["html", "md"])
    view_p.add_argument("--out", default=None)
    view_p.set_defaults(func=cmd_novelty_view)


def _add_common(parser: argparse.ArgumentParser, positive_int) -> None:
    parser.add_argument("--artifact", required=True,
                        help="skill:<path to SKILL.md or its directory>, or text:<path>")
    parser.add_argument("--max-atoms", type=positive_int, default=120, dest="max_atoms",
                        help="Atom cap per artifact. The measurement is LLM-call bound: "
                             "atoms × probes × arms × (answer + grade)")
    parser.add_argument("--all-atoms", action="store_true", dest="all_atoms",
                        help="Extract every atom (opt-in: this is the expensive sweep)")
    parser.add_argument("--budgets", type=float, nargs="+", default=[0.75, 0.5],
                        help="Target token fractions for shortening candidates")
    parser.add_argument("--cache-dir", default=None, dest="cache_dir",
                        help="Disk cache for retention adjudications")
    parser.add_argument("--seed", type=int, default=0,
                        help="Seed for the shuffled control and random selection, so both "
                             "are reproducible across runs")


def _add_model_args(parser: argparse.ArgumentParser, positive_int) -> None:
    parser.add_argument("--model", default="gpt-4o-mini",
                        help="The model under measurement — novelty is a property of the "
                             "(artifact, model) pair, not of the file")
    parser.add_argument("--provider", default="openai", choices=PROVIDERS)
    parser.add_argument("--judge-model", default=None, dest="judge_model",
                        help="Grading model; must differ from --model")
    parser.add_argument("--judge-provider", default=None, dest="judge_provider", choices=PROVIDERS)
    parser.add_argument("--extract-model", default=None, dest="extract_model",
                        help="Extractor/adjudicator model (defaults to --judge-model, so the "
                             "answering model never writes its own answer key)")
    parser.add_argument("--extract-provider", default=None, dest="extract_provider",
                        choices=PROVIDERS)
    parser.add_argument("--max-tokens", type=positive_int, default=None, dest="max_tokens",
                        help="Output-token ceiling. Raise for reasoning models, which can "
                             "spend the provider default on reasoning and return empty text")
    parser.add_argument("--arms", default="no_artifact,full",
                        help="Arms to run: no_artifact,full[,placebo][,shuffled]")
    parser.add_argument("--placebo-text", default=None, dest="placebo_text",
                        help="File of domain-mismatched text for the placebo control: it "
                             "separates 'this artifact carries knowledge' from 'this model "
                             "reacts to any long context'")
    parser.add_argument("--concurrency", type=positive_int, default=5)
    parser.add_argument("--allow-self-judge", action="store_true", dest="allow_self_judge",
                        help="Let the answering model grade itself. Inflates scores; recorded "
                             "as a warning on the artifact")
    parser.add_argument("--no-paraphrase", action="store_true", dest="no_paraphrase")
    parser.add_argument("--no-reversal", action="store_true", dest="no_reversal")


def _clients(args: argparse.Namespace):
    """Build the three role clients, defaulting so roles never silently collapse."""
    judge_model = args.judge_model or _default_judge(args.model)
    judge_provider = args.judge_provider or args.provider
    extract_model = args.extract_model or judge_model
    extract_provider = args.extract_provider or judge_provider
    return (
        _client(extract_model, extract_provider, "extractor", args),
        _client(args.model, args.provider, "answerer", args),
        _client(judge_model, judge_provider, "judge", args),
    )


def _client(model: str, provider: str, role: str, args: argparse.Namespace):
    from agent_benchmarks.novelty.client import LLMClient

    return LLMClient(
        model=model, provider=provider, role=role,
        max_tokens=getattr(args, "max_tokens", None),
    )


def _default_judge(model: str) -> str:
    """A judge that is not the answerer, when the caller did not name one."""
    return "gpt-4o-mini" if model != "gpt-4o-mini" else "gpt-4o"


def _arms(spec: str) -> list[str]:
    arms = [part.strip() for part in spec.split(",") if part.strip()]
    if "no_artifact" not in arms:
        # Without the baseline there is no pair, and without a pair every outcome is a
        # level — which is the one thing the judge agreement does not support.
        raise SystemExit("--arms must include no_artifact: the 2x2 is a paired comparison")
    if "full" not in arms:
        raise SystemExit("--arms must include full: the headline 2x2 pairs it with no_artifact")
    return arms


def _digest(ref: str) -> str | None:
    """The subject scorecard's ``ref_digest``, so one field name means one hash."""
    from agent_benchmarks.subjects.scorecard import _digest_ref

    path = Path(ref.removeprefix("skill:").removeprefix("text:"))
    return _digest_ref(str(path), base=Path.cwd()) if path.exists() else None


def _default_dir(ref: str) -> Path:
    """Where results land when the caller named no output path."""
    return Path("results/novelty") / _safe(ref)


def _safe(ref: str) -> str:
    """A directory name from an artifact reference (`skill:a/b` -> `skill-a-b`)."""
    safe = "".join(c if c.isalnum() or c in "-_." else "-" for c in ref).strip("-.")
    return safe or "artifact"


def _print_headline(artifact: dict) -> None:
    paired = artifact["paired"]
    print(
        f"added: {paired['lenient']['added']} (lenient) / {paired['strict']['added']} (strict), "
        f"already knew: {paired['lenient']['redundant']}, "
        f"degraded: {paired['lenient']['degraded']}, "
        f"dead tokens: {artifact['spans'].get('frac_carrying_nothing')}"
    )
    for warning in artifact.get("warnings", []):
        print(f"WARNING {warning}", file=sys.stderr)
