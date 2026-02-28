#!/usr/bin/env python3
"""CLI for doc-benchmark: run, compare, report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

from doc_benchmarks.report.json_report import write_json
from doc_benchmarks.report.markdown_report import write_compare_report, write_run_report
from doc_benchmarks.runner.compare import compare_snapshots
from doc_benchmarks.runner.run import run_benchmark, save_snapshot
from doc_benchmarks.personas.analyzer import PersonaAnalyzer
from doc_benchmarks.personas.generator import PersonaGenerator


def cmd_run(args: argparse.Namespace) -> None:
    """Run benchmark and save snapshot + report."""
    root = Path(args.root).resolve()
    spec_path = Path(args.spec).resolve()
    out_json = Path(args.out_json).resolve()
    out_md = Path(args.out_md).resolve()

    result = run_benchmark(root, spec_path)
    save_snapshot(result, out_json)
    write_run_report(result, out_md)
    print(json.dumps(result["summary"], indent=2))

    # Strict mode: check hard gate and critical bands
    if args.strict:
        # Re-load spec for gate checks (run_benchmark loads internally)
        import yaml
        spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
        if spec is None:
            spec = {}
        elif not isinstance(spec, dict):
            raise ValueError("Spec must be a YAML mapping/dict")

        from doc_benchmarks.gate.hard_gate import check_hard_gate
        from doc_benchmarks.gate.critical_bands import check_critical_bands

        hard_gate = check_hard_gate(result["summary"], spec)
        bands = check_critical_bands(result["summary"], spec)

        # Exit 1 if hard gate fails
        if hard_gate.enabled and not hard_gate.passed:
            print(f"\n❌ HARD GATE FAILED: score {hard_gate.actual_score:.4f} < {hard_gate.min_score:.4f}", file=sys.stderr)
            sys.exit(1)

        # Exit 1 if any critical band violated
        if bands.has_violations:
            print("\n❌ CRITICAL BAND VIOLATIONS:", file=sys.stderr)
            for v in bands.violations:
                if v.violated:
                    print(f"  - {v.condition}: {v.actual:.4f} < {v.threshold:.4f}", file=sys.stderr)
            sys.exit(1)


def cmd_compare(args: argparse.Namespace) -> None:
    """Compare two snapshots and show regression analysis."""
    base = Path(args.base).resolve()
    cand = Path(args.candidate).resolve()
    spec_path = Path(args.spec).resolve() if args.spec else None
    out_json = Path(args.out_json).resolve()
    out_md = Path(args.out_md).resolve()

    spec_data = None
    if spec_path:
        import yaml
        spec_data = yaml.safe_load(spec_path.read_text(encoding="utf-8"))

    result = compare_snapshots(base, cand, spec=spec_data)
    write_json(result, out_json)
    write_compare_report(result, out_md)
    print(json.dumps(result["diff"], indent=2))


# ─── Baseline management ──────────────────────────────────────────────────────

BASELINES_DIR = Path("baselines/eval")


def _baseline_manifest() -> Dict[str, Any]:
    """Load or create the baseline manifest."""
    manifest_path = BASELINES_DIR / "manifest.json"
    if manifest_path.exists():
        return json.loads(manifest_path.read_text())
    return {"baselines": []}


def _save_manifest(manifest: Dict[str, Any]) -> None:
    BASELINES_DIR.mkdir(parents=True, exist_ok=True)
    (BASELINES_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))


def _compute_summary(eval_data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract key stats from an eval file."""
    evals = eval_data.get("evaluations", [])
    valid = [e for e in evals if e.get("delta") is not None]
    if not valid:
        return {}
    avg_with = sum((e.get("with_docs") or {}).get("aggregate", 0) for e in valid) / len(valid)
    avg_without = sum((e.get("without_docs") or {}).get("aggregate", 0) for e in valid) / len(valid)
    avg_delta = sum(e["delta"] for e in valid) / len(valid)
    return {
        "n": len(valid),
        "avg_with": round(avg_with, 2),
        "avg_without": round(avg_without, 2),
        "avg_delta": round(avg_delta, 2),
    }


def cmd_baseline_save(args: argparse.Namespace) -> None:
    """Save an eval result as a named baseline."""
    from datetime import datetime, timezone

    eval_path = Path(args.from_eval)
    if not eval_path.exists():
        print(f"❌ Eval file not found: {eval_path}")
        raise SystemExit(1)

    eval_data = json.loads(eval_path.read_text())
    product = args.product or eval_data.get("product", "unknown")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    name = args.name or f"{product}-{timestamp}"

    BASELINES_DIR.mkdir(parents=True, exist_ok=True)
    dest = BASELINES_DIR / f"{name}.json"
    dest.write_text(json.dumps(eval_data, indent=2))

    manifest = _baseline_manifest()
    manifest["baselines"].append({
        "name": name,
        "product": product,
        "saved_at": timestamp,
        "path": str(dest),
        "summary": _compute_summary(eval_data),
    })
    _save_manifest(manifest)

    print(f"✅ Saved baseline '{name}' → {dest}")
    summary = _compute_summary(eval_data)
    if summary:
        print(f"   n={summary['n']}  with={summary['avg_with']}  without={summary['avg_without']}  delta={summary['avg_delta']:+}")


def cmd_baseline_list(args: argparse.Namespace) -> None:
    """List all saved baselines."""
    manifest = _baseline_manifest()
    baselines = manifest.get("baselines", [])
    product_filter = getattr(args, "product", None)

    if product_filter:
        baselines = [b for b in baselines if b.get("product") == product_filter]

    if not baselines:
        print("No baselines saved yet.")
        print("Run: python cli.py baseline save --from-eval eval/oneTBB.json --product oneTBB")
        return

    print(f"{'Name':<35} {'Product':<12} {'Saved':<17} {'n':>4} {'with':>6} {'without':>8} {'delta':>7}")
    print("─" * 95)
    for b in baselines:
        s = b.get("summary", {})
        print(
            f"{b['name']:<35} {b.get('product','?'):<12} {b.get('saved_at','?'):<17}"
            f" {s.get('n','?'):>4} {s.get('avg_with','?'):>6} {s.get('avg_without','?'):>8}"
            f" {s.get('avg_delta', 'n/a'):>7}"
        )


def cmd_baseline_compare(args: argparse.Namespace) -> None:
    """Compare an eval result against a saved baseline."""
    eval_path = Path(args.eval)
    if not eval_path.exists():
        print(f"❌ Eval file not found: {eval_path}")
        raise SystemExit(1)

    eval_data = json.loads(eval_path.read_text())
    manifest = _baseline_manifest()
    baselines = manifest.get("baselines", [])

    if not baselines:
        print("No baselines found. Save one first:")
        print("  python cli.py baseline save --from-eval eval/oneTBB.json --product oneTBB")
        raise SystemExit(1)

    # Find baseline: by name or latest for same product
    if args.baseline:
        entry = next((b for b in baselines if b["name"] == args.baseline), None)
        if not entry:
            print(f"❌ Baseline '{args.baseline}' not found.")
            raise SystemExit(1)
    else:
        product = args.product or eval_data.get("product")
        candidates = [b for b in baselines if b.get("product") == product] if product else baselines
        if not candidates:
            candidates = baselines
        entry = candidates[-1]   # most recent

    baseline_data = json.loads(Path(entry["path"]).read_text())
    baseline_evals = {e["question_id"]: e for e in baseline_data.get("evaluations", [])}
    current_evals = eval_data.get("evaluations", [])

    print(f"Comparing against baseline: {entry['name']} (saved {entry.get('saved_at', '?')})\n")

    deltas_changed = []
    for e in current_evals:
        q_id = e["question_id"]
        base_e = baseline_evals.get(q_id)
        if not base_e:
            continue
        cur_delta = e.get("delta")
        base_delta = base_e.get("delta")
        if cur_delta is not None and base_delta is not None:
            change = cur_delta - base_delta
            if abs(change) >= 1:
                deltas_changed.append((q_id, base_delta, cur_delta, change,
                                       e.get("question_text", "")[:60]))

    # Overall summary
    cur_summary = _compute_summary(eval_data)
    base_summary = entry.get("summary", {})

    print(f"{'Metric':<20} {'Baseline':>10} {'Current':>10} {'Change':>8}")
    print("─" * 52)
    for k, label in [("avg_with", "WITH docs avg"), ("avg_without", "WITHOUT avg"), ("avg_delta", "Avg delta")]:
        b_val = base_summary.get(k, "?")
        c_val = cur_summary.get(k, "?")
        try:
            change = f"{c_val - b_val:+.2f}"
        except TypeError:
            change = "?"
        print(f"{label:<20} {str(b_val):>10} {str(c_val):>10} {change:>8}")

    if deltas_changed:
        print(f"\nQuestions with notable changes (|Δ| ≥ 1):")
        print(f"  {'ID':<20} {'base_δ':>7} {'cur_δ':>7} {'change':>7}  Question")
        print("  " + "─" * 80)
        for q_id, bd, cd, ch, txt in sorted(deltas_changed, key=lambda x: -abs(x[3])):
            print(f"  {q_id:<20} {bd:>7} {cd:>7} {ch:>+7}  {txt}")
    else:
        print("\n✅ No notable changes vs baseline.")


def cmd_report(args: argparse.Namespace) -> None:
    """Generate markdown report from JSON snapshot."""
    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    out_md = Path(args.out_md).resolve()

    if "diff" in data:
        write_compare_report(data, out_md)
    else:
        write_run_report(data, out_md)


def cmd_personas_discover(args: argparse.Namespace) -> None:
    """Discover personas for a product by analyzing GitHub repo or a description."""
    import os

    if not args.repo and not args.description:
        print(
            "✗ Either --repo or --description must be provided.",
            file=sys.stderr,
        )
        sys.exit(1)

    generator = PersonaGenerator(model=args.model, provider=args.provider)

    if args.repo:
        # GitHub-based discovery
        github_token = args.github_token or os.getenv("GITHUB_TOKEN")
        analyzer = PersonaAnalyzer(github_token=github_token)
        print(f"Analyzing repository: {args.repo}")
        analysis = analyzer.analyze_repository(args.repo)

        if args.save_analysis:
            output_path = Path(args.output) if args.output else Path(f"personas/{args.product}.json")
            analysis_path = output_path.parent / f"{args.product}_analysis.json"
            analyzer.save_analysis(analysis, analysis_path)
            print(f"✓ Saved analysis to {analysis_path}")
    else:
        # Description-only
        if args.save_analysis:
            print("⚠ --save-analysis is ignored in description-only mode.", file=sys.stderr)
        print(f"No repo — generating personas from description for '{args.product}'")
        analysis = PersonaAnalyzer.create_minimal_analysis(
            library_name=args.product,
            description=args.description,
        )

    # Generate personas
    print(f"Generating personas using {args.model}...")
    personas = generator.generate_personas(
        library_name=args.product,
        analysis=analysis,
        target_count=args.count
    )

    # Save personas
    output_path = Path(args.output) if args.output else Path(f"personas/{args.product}.json")
    generator.save_personas(personas, output_path)

    print(f"\n✓ Generated {len(personas['personas'])} personas for {args.product}")
    print(f"✓ Saved to {output_path}")
    print("\nNext steps:")
    print(f"  1. Review: cat {output_path}")
    print(f"  2. Edit if needed")
    print(f"  3. Approve: python cli.py personas approve --file {output_path}")


def cmd_personas_approve(args: argparse.Namespace) -> None:
    """Mark persona file as approved (ready for question generation)."""
    persona_file = Path(args.file)
    
    if not persona_file.exists():
        print(f"✗ File not found: {persona_file}", file=sys.stderr)
        sys.exit(1)
    
    # Validate JSON structure
    try:
        personas = json.loads(persona_file.read_text())
        required_keys = {"product", "personas"}
        if not required_keys.issubset(personas.keys()):
            print(f"✗ Invalid persona file. Missing keys: {required_keys - personas.keys()}", file=sys.stderr)
            sys.exit(1)
        
        # Check each persona
        for p in personas["personas"]:
            required_fields = {"id", "name", "skill_level"}
            missing = required_fields - set(p.keys())
            if missing:
                print(f"✗ Persona '{p.get('id', '?')}' missing fields: {missing}", file=sys.stderr)
                sys.exit(1)
        
        print(f"✓ Validated {len(personas['personas'])} personas")
        print(f"✓ File approved: {persona_file}")
        print("\nReady for question generation:")
        print(f"  python cli.py questions generate --product {personas['product']} --personas {persona_file}")
        
    except json.JSONDecodeError as e:
        print(f"✗ Invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_questions_analyze(args: argparse.Namespace) -> None:
    """Analyze question quality: difficulty distribution and triviality detection."""
    from doc_benchmarks.questions.quality_analyzer import QuestionQualityAnalyzer

    questions_data = json.loads(Path(args.questions).read_text())
    questions = questions_data.get("questions", questions_data)
    if questions and isinstance(questions[0], dict):
        questions = [q.get("question", q.get("text", str(q))) for q in questions]

    print(f"Analyzing {len(questions)} questions for '{args.product}'...")
    print(f"Model: {args.provider}/{args.model} | concurrency: {args.concurrency}\n")

    analyzer = QuestionQualityAnalyzer(
        model=args.model,
        provider=args.provider,
        concurrency=args.concurrency,
    )
    report = analyzer.analyze(questions, library_name=args.product)

    # Print summary
    dist = report.difficulty_distribution
    print(f"─── Quality Report: {args.product} ───")
    print(f"Total questions : {report.total}")
    print(f"Difficulty      : beginner={dist.get('beginner',0)}  intermediate={dist.get('intermediate',0)}  advanced={dist.get('advanced',0)}")
    print(f"Trivial         : {report.trivial_count} ({report.trivial_pct}%)")
    print(f"Diversity score : {report.diversity_score:.3f}  (1.0 = perfectly balanced)")
    print()
    print("Recommendations:")
    for rec in report.recommendations:
        print(f"  • {rec}")

    if report.trivial_questions:
        print(f"\nTrivial questions ({len(report.trivial_questions)}):")
        for q in report.trivial_questions[:5]:
            print(f"  - {q}")
        if len(report.trivial_questions) > 5:
            print(f"  … and {len(report.trivial_questions) - 5} more (see report file)")

    output_path = Path(args.output) if args.output else Path(f"reports/{args.product}_question_quality.json")
    analyzer.save_report(report, output_path)
    print(f"\n✅ Full report saved to {output_path}")


def cmd_questions_generate(args: argparse.Namespace) -> None:
    """Generate questions from personas and seed topics."""
    import os
    import yaml
    from doc_benchmarks.questions import RagasSeedExtractor, QuestionGenerator, QuestionValidator

    # Load config
    config_path = Path("config/products.yaml")
    if config_path.exists():
        config = yaml.safe_load(config_path.read_text())
    else:
        config = {}
    
    product_config = config.get("products", {}).get(args.product, {})
    
    # Load personas
    personas_data = json.loads(Path(args.personas).read_text())
    personas = personas_data["personas"]
    print(f"Loaded {len(personas)} personas from {args.personas}")
    
    # Get or extract topics
    if args.topics:
        topics = json.loads(Path(args.topics).read_text())
    else:
        print(f"Extracting seed topics for {args.product}...")

        # Setup documentation source client
        doc_source = getattr(args, "doc_source", "context7")
        from doc_benchmarks.mcp.factory import create_doc_source_client
        mcp_client = create_doc_source_client(doc_source)
        context7_id = getattr(args, "context7_id", None)
        if context7_id:
            library_id = context7_id
            print(f"Using explicit Context7 library ID: {library_id}")
        else:
            library_id = mcp_client.resolve_library_id(args.product)

        extractor = RagasSeedExtractor(mcp_client=mcp_client, cache_dir=Path(".cache/topics"))
        topics = extractor.extract_topics(
            library_id=library_id,
            library_name=args.product,
            max_topics=20
        )
        print(f"✓ Extracted {len(topics)} seed topics")
    
    # Generate questions
    print(f"Generating questions using {args.provider}/{args.model}...")
    generator = QuestionGenerator(model=args.model, provider=args.provider)
    
    questions = generator.generate_questions(
        library_name=args.product,
        personas=personas,
        topics=topics,
        questions_per_topic=args.count
    )
    
    print(f"✓ Generated {len(questions)} questions")
    
    # Validate and dedupe (optional)
    if args.validate:
        print("Validating and deduplicating...")
        validator = QuestionValidator(
            llm_model=args.model,
            llm_provider=args.provider,
            threshold=60,
            similarity_threshold=0.85
        )
        
        questions, stats = validator.validate_and_dedupe(args.product, questions)
        
        print(f"✓ Validation complete:")
        print(f"  Initial: {stats['initial_count']}")
        print(f"  After validation: {stats['after_validation']}")
        print(f"  After deduplication: {stats['after_deduplication']}")
        print(f"  Removed (low score): {stats['removed_low_score']}")
        print(f"  Removed (duplicates): {stats['removed_duplicates']}")
    
    # Save output
    output_path = Path(args.output) if args.output else Path(f"questions/{args.product}.json")
    generator.save_questions(questions, output_path)
    
    print(f"\n✅ Saved {len(questions)} questions to {output_path}")


def cmd_answers_generate(args: argparse.Namespace) -> None:
    """Generate answers (WITH and WITHOUT docs) for questions."""
    import yaml
    from doc_benchmarks.eval import Answerer
    from doc_benchmarks.mcp.factory import create_doc_source_client

    # Load config
    config_path = Path("config/products.yaml")
    if config_path.exists():
        config = yaml.safe_load(config_path.read_text())
    else:
        config = {}

    product_config = config.get("products", {}).get(args.product, {})

    # Load questions
    questions_data = json.loads(Path(args.questions).read_text())
    questions = questions_data.get("questions", questions_data)  # Handle both formats
    print(f"Loaded {len(questions)} questions from {args.questions}")

    # Setup documentation source client
    doc_source = getattr(args, "doc_source", "context7")
    print(f"Documentation source: {doc_source}")
    mcp_client = create_doc_source_client(doc_source)
    context7_id = getattr(args, "context7_id", None)
    if context7_id:
        library_id = context7_id
        print(f"Using explicit Context7 library ID: {library_id}")
    else:
        library_id = mcp_client.resolve_library_id(args.product)

    print(f"Generating answers for {args.product} (library_id={library_id})")
    print(f"Using model: {args.provider}/{args.model}")
    
    # Generate answers
    answerer = Answerer(
        mcp_client=mcp_client,
        model=args.model,
        provider=args.provider,
        top_k=args.top_k,
        rerank_threshold=args.rerank_threshold,
        debug_retrieval=args.debug_retrieval
    )
    
    output_path = Path(args.output) if args.output else Path(f"answers/{args.product}.json")

    answers = answerer.generate_answers(
        library_name=args.product,
        library_id=library_id,
        questions=questions,
        max_tokens_per_question=args.max_tokens,
        output_path=output_path,
        concurrency=args.concurrency,
    )

    # generate_answers already saves incrementally to output_path after each
    # question, so the final write here is a safety flush only (ensures the
    # file reflects any last-second ordering fix).
    answerer.save_answers(answers, output_path)
    print(f"\n✅ Saved answers to {output_path}")


def cmd_eval_panel_score(args: argparse.Namespace) -> None:
    """Score answers using a multi-judge panel (parallel, role-diverse judges)."""
    from doc_benchmarks.eval.panel import JudgePanel, JudgeConfig, DEFAULT_PANEL, JUDGE_ROLES

    roles = [r.strip() for r in args.roles.split(",")] if args.roles else DEFAULT_PANEL
    unknown = [r for r in roles if r not in JUDGE_ROLES]
    if unknown:
        print(f"Error: unknown roles: {unknown}. Valid: {list(JUDGE_ROLES)}", file=sys.stderr)
        sys.exit(1)

    judges = [JudgeConfig(role=r, model=args.model, provider=args.provider) for r in roles]
    panel = JudgePanel(judges=judges, concurrency=args.concurrency)

    try:
        answers_data = json.loads(Path(args.answers).read_text())
    except FileNotFoundError:
        print(f"Error: answers file not found: {args.answers}", file=sys.stderr)
        sys.exit(1)
    answers = answers_data.get("answers", answers_data) if isinstance(answers_data, dict) else answers_data
    if not isinstance(answers, list):
        print(f"Error: expected a list of answers in {args.answers}", file=sys.stderr)
        sys.exit(1)
    n_effective = min(len(answers), args.limit) if args.limit else len(answers)
    print(f"Panel evaluation: {n_effective} answers × {len(judges)} judges → {n_effective * len(judges)} LLM calls")
    print(f"Roles: {', '.join(roles)}\nModel: {args.provider}/{args.model}\n")

    output_path = Path(args.output) if args.output else Path(f"eval/{args.product}_panel.json")
    results = panel.evaluate_answers(answers, library_name=args.product,
                                     output_path=output_path,
                                     limit=getattr(args, "limit", None))

    # Summary
    valid = [r for r in results if r.get("with_docs") and r["with_docs"].get("aggregate") is not None]
    if valid:
        mean_score = sum(r["with_docs"]["aggregate"] for r in valid) / len(valid)
        mean_agree = sum(r["with_docs"].get("agreement_score", 1) for r in valid) / len(valid)
        flagged = sum(1 for r in valid if r["with_docs"].get("disagreement_flag", False))
        print(f"\n{'─'*50}")
        print(f"Panel score (with docs):  {mean_score:.1f}/100")
        print(f"Mean agreement score:     {mean_agree:.3f}  (1.0 = perfect)")
        print(f"Disagreement flags:       {flagged}/{len(valid)} questions")

    print(f"\n✅ Saved to {output_path}")


def cmd_eval_score(args: argparse.Namespace) -> None:
    """Evaluate answers using LLM-as-judge."""
    from doc_benchmarks.eval import Judge
    
    # Load answers
    answers_data = json.loads(Path(args.answers).read_text())
    answers = answers_data.get("answers", answers_data)
    print(f"Loaded {len(answers)} answers from {args.answers}")
    
    print(f"Evaluating with judge: {args.judge_provider}/{args.judge_model}")
    
    # Evaluate
    judge = Judge(
        model=args.judge_model,
        provider=args.judge_provider
    )
    
    output_path = Path(args.output) if args.output else Path(f"eval/{args.product}.json")

    evaluations = judge.evaluate_answers(args.product, answers, output_path=output_path, concurrency=args.concurrency)

    judge.save_evaluations(evaluations, output_path)
    print(f"\n✅ Saved evaluations to {output_path}")


def cmd_report_generate(args: argparse.Namespace) -> None:
    """Generate comprehensive analysis report from eval results."""
    from doc_benchmarks.report import ReportGenerator
    
    # Load eval and questions
    eval_data = json.loads(Path(args.eval).read_text())
    questions_data = json.loads(Path(args.questions).read_text())
    
    print(f"Loaded {len(eval_data.get('evaluations', []))} evaluations from {args.eval}")
    print(f"Loaded {len(questions_data.get('questions', []))} questions from {args.questions}")
    
    # Generate report
    generator = ReportGenerator()
    report = generator.generate_report(
        eval_data=eval_data,
        questions_data=questions_data,
        output_format=args.format
    )
    
    # Save output
    output_path = Path(args.output) if args.output else Path(f"reports/{args.product}.{args.format}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report)
    
    print(f"\n✅ Generated report: {output_path}")
    
    # Print summary to console
    if args.format == "markdown":
        print("\n" + "="*80)
        print(report.split("---")[0])  # Print just the summary section


def cmd_evaluate(args: argparse.Namespace) -> None:
    """Run full evaluation pipeline (orchestrator)."""
    from doc_benchmarks.orchestrator import EvaluationPipeline

    if not getattr(args, "repo", None) and not getattr(args, "description", None):
        print("Error: either --repo or --description must be provided.", file=sys.stderr)
        sys.exit(1)

    print(f"Starting full evaluation pipeline for {args.product}")
    if args.repo:
        print(f"Repository: {args.repo}")
    else:
        print(f"Description: {(args.description or '')[:80]}")
    print(f"Output directory: {args.output_dir}")
    if args.custom_questions:
        print(f"Custom questions: {args.custom_questions}")
    print()

    # Create pipeline
    pipeline = EvaluationPipeline(
        product=args.product,
        repo=getattr(args, "repo", None),
        description=getattr(args, "description", None),
        output_dir=Path(args.output_dir),
        custom_questions_path=Path(args.custom_questions) if args.custom_questions else None,
        model=args.model,
        provider=args.provider,
        judge_model=args.judge_model,
        judge_provider=args.judge_provider,
        personas_count=args.personas_count,
        questions_per_topic=args.questions_per_topic,
        top_k=args.top_k,
        rerank_threshold=args.rerank_threshold,
        debug_retrieval=args.debug_retrieval,
        doc_source=getattr(args, "doc_source", "context7"),
        context7_id=getattr(args, "context7_id", None),
    )
    
    # Run pipeline
    try:
        results = pipeline.run()
        
        print("\n" + "="*80)
        print("✅ Pipeline completed successfully!")
        print("="*80)
        print("\nOutput files:")
        print(f"  Personas:   {results['steps']['personas']['path']}")
        print(f"  Questions:  {results['steps']['questions_merged']['path']}")
        print(f"  Answers:    {results['steps']['answers']['path']}")
        print(f"  Evaluation: {results['steps']['evaluation']['path']}")
        print(f"  Report:     {results['steps']['report']['path']}")
        
        if "summary" in results["steps"]["evaluation"]:
            summary = results["steps"]["evaluation"]["summary"]
            print("\nResults:")
            print(f"  WITH docs avg:    {summary['with_avg']}")
            print(f"  WITHOUT docs avg: {summary['without_avg']}")
            print(f"  Delta:            {summary['delta_avg']:+.1f}")
        
        print(f"\n📊 View full report: cat {results['steps']['report']['path']}")
        
    except Exception as e:
        print(f"\n❌ Pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser."""

    def positive_int(value: str) -> int:
        """Argparse type that rejects non-positive integers."""
        try:
            ivalue = int(value)
        except ValueError:
            raise argparse.ArgumentTypeError(f"expected an integer, got '{value}'")
        if ivalue < 1:
            raise argparse.ArgumentTypeError(f"must be >= 1, got {value}")
        return ivalue

    p = argparse.ArgumentParser(prog="doc-benchmark-cli")
    sub = p.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run")
    run_p.add_argument("--root", default=".")
    run_p.add_argument("--spec", default="benchmarks/spec.v1.yaml")
    run_p.add_argument("--out-json", default="baselines/current.json")
    run_p.add_argument("--out-md", default="reports/current.md")
    run_p.add_argument("--strict", action="store_true", help="Enable hard gate and critical bands (exit 1 on failure)")
    run_p.set_defaults(func=cmd_run)

    # evaluate (orchestrator) - full pipeline
    eval_p = sub.add_parser("evaluate", help="Run full evaluation pipeline (one command)")
    eval_p.add_argument("--product", required=True, help="Product name (e.g., oneDNN)")
    eval_p.add_argument("--repo", default=None, help="GitHub repo (e.g., oneapi-src/oneDNN). Optional if --description is given.")
    eval_p.add_argument("--description", default=None, help="Plain-text product description (used when --repo is not available).")
    eval_p.add_argument("--output-dir", default=".", help="Base output directory")
    eval_p.add_argument("--custom-questions", default=None, help="Optional: path to manual questions JSON")
    eval_p.add_argument("--model", default="gpt-4o-mini", help="LLM model for generation/answering")
    eval_p.add_argument("--provider", default="openai", choices=["openai", "anthropic"])
    eval_p.add_argument("--judge-model", default="gpt-4o-mini", help="LLM model for evaluation")
    eval_p.add_argument("--judge-provider", default="openai", choices=["openai", "anthropic"])
    eval_p.add_argument("--personas-count", type=int, default=5, help="Target number of personas")
    eval_p.add_argument("--questions-per-topic", type=int, default=2, help="Questions per topic per persona")
    eval_p.add_argument("--top-k", type=int, default=5, help="Docs to retrieve before reranking")
    eval_p.add_argument("--rerank-threshold", type=float, default=0.3, help="Min relevance score")
    eval_p.add_argument("--debug-retrieval", action="store_true", help="Include retrieval metadata")
    eval_p.add_argument("--doc-source", default="context7",
                        help="Documentation source: 'context7' (default), 'local:<path>', 'url:<url>'")
    eval_p.add_argument("--context7-id", default=None, dest="context7_id",
                        help="Explicit Context7 library ID (e.g., 'intel/mkl-dnn'). Overrides auto-resolution.")
    eval_p.set_defaults(func=cmd_evaluate)

    cmp_p = sub.add_parser("compare")
    cmp_p.add_argument("--base", required=True)
    cmp_p.add_argument("--candidate", required=True)
    cmp_p.add_argument("--spec", default=None, help="Spec file for regression thresholds")
    cmp_p.add_argument("--out-json", default="reports/compare.json")
    cmp_p.add_argument("--out-md", default="reports/compare.md")
    cmp_p.set_defaults(func=cmd_compare)

    # Baseline subcommand group
    bl_p = sub.add_parser("baseline", help="Save and compare eval baselines")
    bl_sub = bl_p.add_subparsers(dest="baseline_cmd", required=True)

    # baseline save
    bl_save = bl_sub.add_parser("save", help="Save an eval result as a named baseline")
    bl_save.add_argument("--from-eval", required=True, help="Path to eval JSON file")
    bl_save.add_argument("--product", default=None, help="Product name (e.g., oneTBB)")
    bl_save.add_argument("--name", default=None, help="Baseline name (auto-generated if omitted)")
    bl_save.set_defaults(func=cmd_baseline_save)

    # baseline list
    bl_list = bl_sub.add_parser("list", help="List saved baselines")
    bl_list.add_argument("--product", default=None, help="Filter by product")
    bl_list.set_defaults(func=cmd_baseline_list)

    # baseline compare
    bl_cmp = bl_sub.add_parser("compare", help="Compare eval result vs saved baseline")
    bl_cmp.add_argument("--eval", required=True, help="Path to current eval JSON file")
    bl_cmp.add_argument("--product", default=None, help="Product name for baseline lookup")
    bl_cmp.add_argument("--baseline", default=None, help="Baseline name (latest if omitted)")
    bl_cmp.set_defaults(func=cmd_baseline_compare)

    # Report subcommand group
    report_p = sub.add_parser("report", help="Generate analysis reports")
    report_sub = report_p.add_subparsers(dest="report_cmd", required=True)
    
    # report generate
    gen_r_p = report_sub.add_parser("generate", help="Generate comprehensive report from eval results")
    gen_r_p.add_argument("--product", required=True, help="Product name (e.g., oneTBB)")
    gen_r_p.add_argument("--eval", required=True, help="Path to eval JSON file")
    gen_r_p.add_argument("--questions", required=True, help="Path to questions JSON file")
    gen_r_p.add_argument("--output", default=None, help="Output file (default: reports/{product}.md)")
    gen_r_p.add_argument("--format", default="markdown", choices=["markdown", "json"], help="Output format")
    gen_r_p.set_defaults(func=cmd_report_generate)

    # Personas subcommand group
    personas_p = sub.add_parser("personas", help="Persona discovery and management")
    personas_sub = personas_p.add_subparsers(dest="personas_cmd", required=True)
    
    # personas discover
    discover_p = personas_sub.add_parser("discover", help="Discover personas from a GitHub repo or product description")
    discover_p.add_argument("--product", required=True, help="Product name (e.g., oneTBB)")
    discover_p.add_argument("--repo", default=None, help="GitHub repo (e.g., uxlfoundation/oneTBB). Optional if --description is given.")
    discover_p.add_argument("--description", default=None, help="Plain-text product description (used when --repo is not available).")
    discover_p.add_argument("--output", default=None, help="Output file (default: personas/{product}.json)")
    discover_p.add_argument("--count", type=int, default=5, help="Target number of personas (5-8)")
    discover_p.add_argument("--model", default="gpt-4o-mini", help="LLM model for generation")
    discover_p.add_argument("--provider", default="openai", choices=["openai", "anthropic"])
    discover_p.add_argument("--github-token", default=None, help="GitHub token (or set GITHUB_TOKEN env)")
    discover_p.add_argument("--save-analysis", action="store_true", help="Save intermediate analysis JSON")
    discover_p.set_defaults(func=cmd_personas_discover)
    
    # personas approve
    approve_p = personas_sub.add_parser("approve", help="Validate and approve persona file")
    approve_p.add_argument("--file", required=True, help="Persona JSON file to approve")
    approve_p.set_defaults(func=cmd_personas_approve)
    
    # Questions subcommand group
    questions_p = sub.add_parser("questions", help="Question generation")
    questions_sub = questions_p.add_subparsers(dest="questions_cmd", required=True)
    
    # questions generate
    gen_q_p = questions_sub.add_parser("generate", help="Generate questions from personas and topics")
    gen_q_p.add_argument("--product", required=True, help="Product name (e.g., oneTBB)")
    gen_q_p.add_argument("--personas", required=True, help="Path to personas JSON file")
    gen_q_p.add_argument("--output", default=None, help="Output file (default: questions/{product}.json)")
    gen_q_p.add_argument("--topics", default=None, help="Optional: path to topics JSON (auto-extracted if not provided)")
    gen_q_p.add_argument("--count", type=int, default=2, help="Questions per topic per persona")
    gen_q_p.add_argument("--validate", action="store_true", help="Enable validation and deduplication")
    gen_q_p.add_argument("--model", default="gpt-4o-mini", help="LLM model for generation")
    gen_q_p.add_argument("--provider", default="openai", choices=["openai", "anthropic"])
    gen_q_p.add_argument("--doc-source", default="context7",
                         help="Documentation source for topic extraction: 'context7', 'local:<path>', 'url:<url>'")
    gen_q_p.add_argument("--context7-id", default=None, dest="context7_id",
                         help="Explicit Context7 library ID. Overrides auto-resolution.")
    gen_q_p.set_defaults(func=cmd_questions_generate)

    # questions analyze
    analyze_q_p = questions_sub.add_parser("analyze", help="Analyze question quality (difficulty + triviality)")
    analyze_q_p.add_argument("--questions", required=True, help="Path to questions JSON file")
    analyze_q_p.add_argument("--product", required=True, help="Product name (e.g., oneTBB)")
    analyze_q_p.add_argument("--output", default=None, help="Output report JSON (default: reports/{product}_question_quality.json)")
    analyze_q_p.add_argument("--model", default="gpt-4o-mini", help="LLM model for classification")
    analyze_q_p.add_argument("--provider", default="openai", choices=["openai", "anthropic"])
    analyze_q_p.add_argument("--concurrency", type=int, default=5, help="Parallel classification requests")
    analyze_q_p.set_defaults(func=cmd_questions_analyze)

    # Answers subcommand group
    answers_p = sub.add_parser("answers", help="Answer generation")
    answers_sub = answers_p.add_subparsers(dest="answers_cmd", required=True)
    
    # answers generate
    gen_a_p = answers_sub.add_parser("generate", help="Generate answers (WITH and WITHOUT docs)")
    gen_a_p.add_argument("--product", required=True, help="Product name (e.g., oneTBB)")
    gen_a_p.add_argument("--questions", required=True, help="Path to questions JSON file")
    gen_a_p.add_argument("--output", default=None, help="Output file (default: answers/{product}.json)")
    gen_a_p.add_argument("--model", default="gpt-4o", help="LLM model for answering")
    gen_a_p.add_argument("--provider", default="openai", choices=["openai", "anthropic"])
    gen_a_p.add_argument("--max-tokens", type=int, default=4000, help="Max tokens to retrieve per question")
    gen_a_p.add_argument("--top-k", type=int, default=5, help="Number of docs to retrieve before reranking")
    gen_a_p.add_argument("--rerank-threshold", type=float, default=0.3, help="Min relevance score (0-1) to keep docs")
    gen_a_p.add_argument("--debug-retrieval", action="store_true", help="Include retrieval metadata in output")
    gen_a_p.add_argument("--concurrency", type=positive_int, default=5, help="Parallel API calls (default: 5)")
    gen_a_p.add_argument("--doc-source", default="context7",
                         help="Documentation source: 'context7' (default), 'local:<path>', 'url:<url>'")
    gen_a_p.add_argument("--context7-id", default=None, dest="context7_id",
                         help="Explicit Context7 library ID. Overrides auto-resolution.")
    gen_a_p.set_defaults(func=cmd_answers_generate)
    
    # Eval subcommand group
    eval_p = sub.add_parser("eval", help="Evaluate answers")
    eval_sub = eval_p.add_subparsers(dest="eval_cmd", required=True)
    
    # eval score
    score_p = eval_sub.add_parser("score", help="Score answers using LLM-as-judge")
    score_p.add_argument("--product", required=True, help="Product name (e.g., oneTBB)")
    score_p.add_argument("--answers", required=True, help="Path to answers JSON file")
    score_p.add_argument("--output", default=None, help="Output file (default: eval/{product}.json)")
    score_p.add_argument("--judge-model", default="claude-sonnet-4", help="LLM model for judging")
    score_p.add_argument("--judge-provider", default="anthropic", choices=["openai", "anthropic"])
    score_p.add_argument("--concurrency", type=positive_int, default=5, help="Parallel judge calls (default: 5)")
    score_p.set_defaults(func=cmd_eval_score)

    # eval panel-score
    panel_p = eval_sub.add_parser("panel-score", help="Score answers using a multi-judge panel")
    panel_p.add_argument("--answers", required=True, help="Path to answers JSON file")
    panel_p.add_argument("--product", required=True, help="Product name (e.g., oneTBB)")
    panel_p.add_argument("--output", default=None, help="Output file (default: eval/{product}_panel.json)")
    panel_p.add_argument("--model", default="gpt-4o-mini", help="Default LLM model for all judges")
    panel_p.add_argument("--provider", default="openai", choices=["openai", "anthropic"])
    panel_p.add_argument("--roles", default=None,
                         help="Comma-separated judge roles (default: technical_expert,developer_advocate,doc_reviewer)")
    panel_p.add_argument("--concurrency", type=positive_int, default=6,
                         help="Parallel judge API calls (default: 6)")
    panel_p.add_argument("--limit", type=positive_int, default=None,
                         help="Evaluate only first N answers (useful for testing)")
    panel_p.set_defaults(func=cmd_eval_panel_score)

    # library subcommand group
    library_p = sub.add_parser("library", help="Library registry management")
    library_sub = library_p.add_subparsers(dest="library_cmd", required=True)

    lib_list_p = library_sub.add_parser("list", help="List libraries in the registry")
    lib_list_p.add_argument("--registry", default=None, help="Path to custom libraries.yaml")
    lib_list_p.set_defaults(func=cmd_library_list)

    lib_show_p = library_sub.add_parser("show", help="Show details for a library")
    lib_show_p.add_argument("name", help="Library key (e.g., onetbb)")
    lib_show_p.add_argument("--registry", default=None, help="Path to custom libraries.yaml")
    lib_show_p.set_defaults(func=cmd_library_show)

    # benchmark subcommand group
    benchmark_p = sub.add_parser("benchmark", help="Run benchmark for one or all registered libraries")
    benchmark_sub = benchmark_p.add_subparsers(dest="benchmark_cmd", required=True)

    # benchmark run — single library from registry
    bench_run_p = benchmark_sub.add_parser("run", help="Run full pipeline for a registered library")
    bench_run_p.add_argument("--library", required=True, help="Library key from registry (e.g., onetbb)")
    bench_run_p.add_argument("--doc-source", default=None, dest="doc_source",
                             help="Override doc source (default: first in registry entry)")
    bench_run_p.add_argument("--output-dir", default=None, dest="output_dir",
                             help="Output directory (default: results/{library})")
    bench_run_p.add_argument("--model", default="gpt-4o-mini")
    bench_run_p.add_argument("--provider", default="openai", choices=["openai", "anthropic"])
    bench_run_p.add_argument("--judge-model", default="claude-sonnet-4", dest="judge_model")
    bench_run_p.add_argument("--registry", default=None, help="Path to custom libraries.yaml")
    bench_run_p.set_defaults(func=cmd_benchmark_run)

    # benchmark batch — multiple libraries
    bench_batch_p = benchmark_sub.add_parser("batch", help="Run pipeline for multiple libraries")
    bench_batch_p.add_argument("--libraries", default=None,
                               help="Comma-separated library keys (e.g., onetbb,onemkl). "
                                    "Omit or use --all for all registered libraries.")
    bench_batch_p.add_argument("--all", action="store_true", dest="all_libraries",
                               help="Run for all libraries in registry")
    bench_batch_p.add_argument("--output-dir", default="results", dest="output_dir")
    bench_batch_p.add_argument("--model", default="gpt-4o-mini")
    bench_batch_p.add_argument("--provider", default="openai", choices=["openai", "anthropic"])
    bench_batch_p.add_argument("--judge-model", default="claude-sonnet-4", dest="judge_model")
    bench_batch_p.add_argument("--registry", default=None, help="Path to custom libraries.yaml")
    bench_batch_p.add_argument("--fail-fast", action="store_true", dest="fail_fast",
                               help="Stop on first failure (default: continue all)")
    bench_batch_p.set_defaults(func=cmd_benchmark_batch)

    # dashboard subcommand
    dashboard_p = sub.add_parser("dashboard", help="Generate dashboard from evaluation results")
    dashboard_sub = dashboard_p.add_subparsers(dest="dashboard_cmd", required=True)

    dash_gen_p = dashboard_sub.add_parser("generate", help="Generate Markdown + JSON dashboard")
    dash_gen_p.add_argument("--results-dir", default="results", dest="results_dir",
                            help="Directory with evaluation results (default: results/)")
    dash_gen_p.add_argument("--output-dir", default=".", dest="output_dir",
                            help="Where to write DASHBOARD.md + dashboard.json (default: .)")
    dash_gen_p.add_argument("--top-n", type=positive_int, default=5, dest="top_n",
                            help="Bad questions to show per product (default: 5)")
    dash_gen_p.add_argument("--no-json", action="store_true", dest="no_json",
                            help="Skip JSON output")
    dash_gen_p.set_defaults(func=cmd_dashboard_generate)

    return p


def cmd_dashboard_generate(args: argparse.Namespace) -> None:
    """Aggregate evaluation results and render Markdown + JSON dashboard."""
    from doc_benchmarks.dashboard.aggregator import ResultsAggregator
    from doc_benchmarks.dashboard.markdown_renderer import render_dashboard, save_dashboard_markdown, save_dashboard_json

    results_dir = Path(args.results_dir)
    output_dir = Path(args.output_dir)

    print(f"Scanning results in: {results_dir}")
    aggregator = ResultsAggregator(results_dir)
    data = aggregator.aggregate()

    if not data.products:
        print("⚠ No evaluation results found. Run benchmark first.", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(data.products)} product(s): {', '.join(p.product for p in data.products)}")

    md_path = output_dir / "DASHBOARD.md"
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_dashboard(data, top_n_bad_questions=args.top_n))
    print(f"✅ Markdown dashboard: {md_path}")

    if not args.no_json:
        json_path = output_dir / "dashboard.json"
        save_dashboard_json(data, json_path)
        print(f"✅ JSON data:          {json_path}")

    # Print quick summary to stdout
    print(f"\n{'─'*50}")
    print(f"{'Product':<30} {'Score':>6}  {'Status'}")
    print(f"{'─'*50}")
    for p in data.sorted_by_score:
        score = f"{p.doc_score:.1f}" if p.doc_score is not None else "  n/a"
        status_icon = {"good": "🟢", "fair": "🟡", "poor": "🔴", "no-data": "⚪"}.get(p.status, "⚪")
        print(f"{p.product:<30} {score:>6}  {status_icon}")


def _load_registry(args):
    from doc_benchmarks.registry import LibraryRegistry
    from pathlib import Path as _Path
    reg_path = _Path(args.registry) if getattr(args, "registry", None) else None
    return LibraryRegistry(path=reg_path)


def cmd_library_list(args: argparse.Namespace) -> None:
    """List all libraries in the registry."""
    registry = _load_registry(args)
    entries = registry.list()
    if not entries:
        print("Registry is empty.")
        return
    print(f"{'Key':<12} {'Name':<16} {'Repo':<35} {'Doc sources'}")
    print("─" * 85)
    for e in entries:
        repo = e.repo or "—"
        sources = ", ".join(e.doc_sources)
        print(f"{e.key:<12} {e.name:<16} {repo:<35} {sources}")
    print(f"\n{len(entries)} libraries registered.")


def cmd_library_show(args: argparse.Namespace) -> None:
    """Show full details for a single library."""
    registry = _load_registry(args)
    try:
        entry = registry.get(args.name)
    except KeyError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"Key          : {entry.key}")
    print(f"Name         : {entry.name}")
    print(f"Repo         : {entry.repo or '—'}")
    print(f"Context7 ID  : {entry.context7_id or '—'}")
    print(f"Doc sources  : {', '.join(entry.doc_sources)}")
    print(f"Description  :\n  {entry.description}")


def _run_single_library(entry, output_dir: str, model: str, provider: str, judge_model: str, doc_source_override=None) -> dict:
    """Run full evaluation pipeline for one LibraryEntry. Returns result dict."""
    from doc_benchmarks.orchestrator import EvaluationPipeline
    from pathlib import Path as _Path

    doc_source = doc_source_override or (entry.doc_sources[0] if entry.doc_sources else "context7")
    out = _Path(output_dir)

    print(f"\n{'='*60}")
    print(f"  Library : {entry.name} ({entry.key})")
    print(f"  Source  : {doc_source}")
    print(f"  Output  : {out}")
    print(f"{'='*60}")

    pipeline = EvaluationPipeline(
        product=entry.name,
        repo=entry.repo,
        description=entry.description,
        output_dir=out,
        model=model,
        provider=provider,
        judge_model=judge_model,
        context7_id=entry.context7_id,
        doc_source=doc_source,
    )
    result = pipeline.run()
    return {"library": entry.key, "name": entry.name, "status": "ok", "result": result}


def cmd_benchmark_run(args: argparse.Namespace) -> None:
    """Run full evaluation pipeline for a single registered library."""
    registry = _load_registry(args)
    try:
        entry = registry.get(args.library)
    except KeyError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    output_dir = args.output_dir or f"results/{entry.key}"
    _run_single_library(
        entry,
        output_dir=output_dir,
        model=args.model,
        provider=args.provider,
        judge_model=args.judge_model,
        doc_source_override=getattr(args, "doc_source", None),
    )
    print(f"\n✅ Done: {entry.name}")


def cmd_benchmark_batch(args: argparse.Namespace) -> None:
    """Run evaluation pipeline for multiple registered libraries."""
    registry = _load_registry(args)

    if args.all_libraries or not args.libraries:
        entries = registry.list()
    else:
        keys = [k.strip() for k in args.libraries.split(",") if k.strip()]
        entries = []
        for k in keys:
            try:
                entries.append(registry.get(k))
            except KeyError as exc:
                print(f"Warning: {exc}", file=sys.stderr)

    if not entries:
        print("No libraries to run.", file=sys.stderr)
        sys.exit(1)

    print(f"Batch run: {len(entries)} libraries → {args.output_dir}")
    results = []
    failed = []

    for entry in entries:
        try:
            r = _run_single_library(
                entry,
                output_dir=args.output_dir,
                model=args.model,
                provider=args.provider,
                judge_model=args.judge_model,
            )
            results.append(r)
        except Exception as exc:
            msg = f"FAILED: {entry.key} — {exc}"
            print(f"\n❌ {msg}", file=sys.stderr)
            failed.append({"library": entry.key, "name": entry.name, "status": "failed", "error": str(exc)})
            if args.fail_fast:
                print("Stopping (--fail-fast).", file=sys.stderr)
                break

    # Summary
    print(f"\n{'─'*50}")
    print(f"Batch complete: {len(results)} succeeded, {len(failed)} failed")
    for r in results:
        print(f"  ✅ {r['name']}")
    for f in failed:
        print(f"  ❌ {f['name']}: {f['error']}")

    if failed:
        sys.exit(1)


def main() -> None:
    """Entry point."""
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
