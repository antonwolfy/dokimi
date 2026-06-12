"""benchmark subcommand group: run, batch."""

from __future__ import annotations

import argparse
import sys

from doc_benchmarks.commands.evaluate import _warn_judge_independence
from doc_benchmarks.commands.library import _load_registry


def _run_single_library(entry, output_dir: str, model: str, provider: str, judge_model: str, judge_provider: str = "openai", doc_source_override=None, max_tokens_per_question: int = 4000, force_regen: bool = False, concurrency: int = 5, questions_from=None) -> dict:
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

    _warn_judge_independence(
        answer_provider=provider,
        answer_model=model,
        judge_provider=judge_provider,
        judge_model=judge_model,
        context=f"benchmark:{entry.key}",
    )

    pipeline = EvaluationPipeline(
        product=entry.name,
        repo=entry.repo,
        description=entry.description,
        output_dir=out,
        model=model,
        provider=provider,
        judge_model=judge_model,
        judge_provider=judge_provider,
        context7_id=entry.context7_id,
        doc_source=doc_source,
        max_tokens_per_question=max_tokens_per_question,
        force_regen=force_regen,
        questions_from=questions_from,
    )
    result = pipeline.run(concurrency=concurrency)
    return {"library": entry.key, "name": entry.name, "status": "ok", "result": result}


def cmd_benchmark_run(args: argparse.Namespace) -> None:
    """Run full evaluation pipeline for a single registered library."""
    import statistics as _stats
    registry = _load_registry(args)
    try:
        entry = registry.get(args.library)
    except KeyError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    output_dir = args.output_dir or f"results/{entry.key}"
    n_runs = getattr(args, "multi_run", 1)
    concurrency = getattr(args, "concurrency", 5)
    questions_from = getattr(args, "questions_from", None)

    if n_runs == 1:
        _run_single_library(
            entry,
            output_dir=output_dir,
            model=args.model,
            provider=args.provider,
            judge_model=args.judge_model,
            judge_provider=getattr(args, "judge_provider", "openai"),
            doc_source_override=getattr(args, "doc_source", None),
            max_tokens_per_question=getattr(args, "max_tokens", 4000),
            force_regen=getattr(args, "force_regen", False),
            concurrency=concurrency,
            questions_from=questions_from,
        )
    else:
        print(f"\n🔁 Multi-run mode: {n_runs} evaluation passes")
        run_averages = []
        first_run_dir = f"{output_dir}_run1"
        for i in range(1, n_runs + 1):
            run_dir = f"{output_dir}_run{i}" if n_runs > 1 else output_dir
            qfrom = questions_from if questions_from else (first_run_dir if i > 1 else None)
            print(f"\n  ── Run {i}/{n_runs} → {run_dir}")
            r = _run_single_library(
                entry,
                output_dir=run_dir,
                model=args.model,
                provider=args.provider,
                judge_model=args.judge_model,
                judge_provider=getattr(args, "judge_provider", "openai"),
                doc_source_override=getattr(args, "doc_source", None),
                max_tokens_per_question=getattr(args, "max_tokens", 4000),
                force_regen=(getattr(args, "force_regen", False) and i == 1),
                concurrency=concurrency,
                questions_from=qfrom,
            )
            try:
                eval_summary = r["result"]["steps"]["evaluation"]["summary"]
                run_averages.append(eval_summary["with_avg"])
            except (KeyError, TypeError):
                pass
        if run_averages:
            import statistics as _stats
            std = _stats.stdev(run_averages) if len(run_averages) > 1 else 0.0
            mean = _stats.mean(run_averages)
            print(f"\n📊 Multi-run summary ({n_runs} runs): context-arm avg {mean:.1f} ± {std:.2f}")
            if std > 5.0:
                print("   ⚠️  High variance — scores are unstable (std > 5)")

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
                judge_provider=getattr(args, "judge_provider", "openai"),
                max_tokens_per_question=getattr(args, "max_tokens", 4000),
                force_regen=getattr(args, "force_regen", False),
                concurrency=getattr(args, "concurrency", 5),
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


def register(sub, positive_int) -> None:
    """Add the `benchmark` subcommand group."""
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
    bench_run_p.add_argument("--provider", default="openai", choices=["openai", "anthropic", "amazon-bedrock", "google-vertex", "openrouter", "openai-codex"])
    bench_run_p.add_argument("--judge-model", default="gpt-4o-mini", dest="judge_model")
    bench_run_p.add_argument("--judge-provider", default="openai", dest="judge_provider",
                             choices=["openai", "anthropic", "amazon-bedrock", "google-vertex", "openrouter", "openai-codex"])
    bench_run_p.add_argument("--registry", default=None, help="Path to custom libraries.yaml")
    bench_run_p.add_argument("--max-tokens", type=positive_int, default=4000, dest="max_tokens",
                             help="Max tokens to retrieve per question from doc source (default: 4000)")
    bench_run_p.add_argument("--concurrency", type=positive_int, default=5, dest="concurrency",
                             help="Parallel API calls for answering and judging (default: 5)")
    bench_run_p.add_argument("--force-regen", action="store_true", dest="force_regen",
                             help="Regenerate personas/questions even if cached files exist")
    bench_run_p.add_argument("--questions-from", default=None, dest="questions_from",
                             help="Reuse questions from another run's output directory or JSON file. "
                                  "Skips question generation entirely — essential for fair multi-model "
                                  "comparisons (all models evaluated on the same question set). "
                                  "Example: --questions-from results/onedal_gpt4o")
    bench_run_p.add_argument("--multi-run", type=positive_int, default=1, dest="multi_run",
                             metavar="N",
                             help="Run answer generation + evaluation N times (default: 1). "
                                  "N>=3 enables variance check in the trust gate. "
                                  "Results are averaged; variance is measured for stability.")
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
    bench_batch_p.add_argument("--provider", default="openai", choices=["openai", "anthropic", "amazon-bedrock", "google-vertex", "openrouter", "openai-codex"])
    bench_batch_p.add_argument("--judge-model", default="gpt-4o-mini", dest="judge_model")
    bench_batch_p.add_argument("--judge-provider", default="openai", dest="judge_provider",
                               choices=["openai", "anthropic", "amazon-bedrock", "google-vertex", "openrouter", "openai-codex"])
    bench_batch_p.add_argument("--max-tokens", type=positive_int, default=4000, dest="max_tokens",
                               help="Max tokens to retrieve per question from doc source (default: 4000)")
    bench_batch_p.add_argument("--force-regen", action="store_true", dest="force_regen",
                               help="Regenerate personas/questions even if cached files exist")
    bench_batch_p.add_argument("--registry", default=None, help="Path to custom libraries.yaml")
    bench_batch_p.add_argument("--fail-fast", action="store_true", dest="fail_fast",
                               help="Stop on first failure (default: continue all)")
    bench_batch_p.set_defaults(func=cmd_benchmark_batch)
