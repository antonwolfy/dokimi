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
    """Discover personas for a product by analyzing GitHub repo."""
    import os
    
    # Initialize analyzer
    github_token = args.github_token or os.getenv("GITHUB_TOKEN")
    analyzer = PersonaAnalyzer(github_token=github_token)
    
    # Analyze repository
    print(f"Analyzing repository: {args.repo}")
    analysis = analyzer.analyze_repository(args.repo)
    
    # Save analysis if requested
    if args.save_analysis:
        analysis_path = Path(args.output).parent / f"{args.product}_analysis.json"
        analyzer.save_analysis(analysis, analysis_path)
        print(f"✓ Saved analysis to {analysis_path}")
    
    # Generate personas
    print(f"Generating personas using {args.model}...")
    generator = PersonaGenerator(model=args.model, provider=args.provider)
    
    personas = generator.generate_personas(
        library_name=args.product,
        analysis=analysis,
        target_count=args.count
    )
    
    # Save personas
    output_path = Path(args.output)
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


def cmd_questions_generate(args: argparse.Namespace) -> None:
    """Generate questions from personas and seed topics."""
    import os
    import yaml
    from doc_benchmarks.questions import RagasSeedExtractor, QuestionGenerator, QuestionValidator
    from doc_benchmarks.mcp.context7 import create_context7_client
    
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
        
        # Setup Context7 MCP client
        mcp_client = create_context7_client(cache_dir=Path(".cache/context7"))
        library_id = mcp_client.resolve_library_id(args.product)
        
        # Extract topics
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
    from doc_benchmarks.mcp.context7 import create_context7_client
    
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
    
    # Setup Context7 MCP client
    mcp_client = create_context7_client(cache_dir=Path(".cache/context7"))
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

    answerer.save_answers(answers, output_path)
    print(f"\n✅ Saved answers to {output_path}")


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
    
    print(f"Starting full evaluation pipeline for {args.product}")
    print(f"Repository: {args.repo}")
    print(f"Output directory: {args.output_dir}")
    if args.custom_questions:
        print(f"Custom questions: {args.custom_questions}")
    print()
    
    # Create pipeline
    pipeline = EvaluationPipeline(
        product=args.product,
        repo=args.repo,
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
        debug_retrieval=args.debug_retrieval
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
    eval_p.add_argument("--repo", required=True, help="GitHub repo (e.g., oneapi-src/oneDNN)")
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
    discover_p = personas_sub.add_parser("discover", help="Auto-discover personas from GitHub repo")
    discover_p.add_argument("--product", required=True, help="Product name (e.g., oneTBB)")
    discover_p.add_argument("--repo", required=True, help="GitHub repo (e.g., uxlfoundation/oneTBB)")
    discover_p.add_argument("--output", default=None, help="Output file (default: personas/{product}.json)")
    discover_p.add_argument("--count", type=int, default=5, help="Target number of personas (5-8)")
    discover_p.add_argument("--model", default="gpt-4o-mini", help="LLM model for generation")
    discover_p.add_argument("--provider", default="openai", choices=["openai", "anthropic"])
    discover_p.add_argument("--github-token", default=None, help="GitHub token (or set GITHUB_TOKEN env)")
    discover_p.add_argument("--save-analysis", action="store_true", help="Save intermediate analysis JSON")
    discover_p.set_defaults(func=cmd_personas_discover)
    
    # Set default output path if not provided
    def set_default_output(args):
        if args.output is None:
            args.output = f"personas/{args.product}.json"
        return args
    
    discover_p.set_defaults(func=lambda args: cmd_personas_discover(set_default_output(args)))
    
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
    gen_q_p.set_defaults(func=cmd_questions_generate)
    
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
    gen_a_p.add_argument("--concurrency", type=int, default=5, help="Parallel API calls (default: 5)")
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
    score_p.add_argument("--concurrency", type=int, default=5, help="Parallel judge calls (default: 5)")
    score_p.set_defaults(func=cmd_eval_score)

    return p


def main() -> None:
    """Entry point."""
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
