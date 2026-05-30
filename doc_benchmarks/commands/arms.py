"""arms subcommand group: run (N-way treatment comparison)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def cmd_arms_run(args: argparse.Namespace) -> None:
    """Run an N-arm treatment comparison and optionally judge it."""
    from doc_benchmarks.treatments import create_treatments
    from doc_benchmarks.eval.arm_runner import ArmRunner
    from doc_benchmarks.report.arms_report import render_arms_report

    specs = [s.strip() for s in args.arms.split(",") if s.strip()]
    if not specs:
        print("Error: --arms must list at least one arm spec.", file=sys.stderr)
        sys.exit(1)

    questions_data = json.loads(Path(args.questions).read_text())
    if isinstance(questions_data, dict):
        questions = questions_data.get("questions", questions_data)
    else:
        questions = questions_data
    if not isinstance(questions, list):
        print(f"Error: expected a list of questions in {args.questions}", file=sys.stderr)
        sys.exit(1)
    print(f"Loaded {len(questions)} questions from {args.questions}")

    try:
        treatments = create_treatments(
            specs, top_k=args.top_k, rerank_threshold=args.rerank_threshold
        )
    except (ValueError, FileNotFoundError) as exc:
        print(f"Error building arms: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"Arms: {', '.join(t.name for t in treatments)}")

    # Resolve a library id for any doc/MCP arms (best-effort; safe to skip).
    library_id = args.context7_id
    if library_id is None:
        from doc_benchmarks.treatments.arms import DocTreatment
        for t in treatments:
            if isinstance(t, DocTreatment):
                try:
                    library_id = t.mcp_client.resolve_library_id(args.product)
                except Exception:
                    library_id = args.product
                break

    runner = ArmRunner(treatments, model=args.model, provider=args.provider,
                       max_iterations=args.max_iterations)
    records = runner.run(
        library_name=args.product,
        questions=questions,
        library_id=library_id,
        concurrency=args.concurrency,
    )

    evaluations = None
    if args.judge:
        from doc_benchmarks.eval import Judge
        judge = Judge(model=args.judge_model, provider=args.judge_provider)
        print("Judging arms…")
        evaluations = runner.judge(
            judge, args.product, records,
            baseline_arm=args.baseline_arm, concurrency=args.concurrency,
        )

    output = runner.build_output(
        args.product, records, evaluations=evaluations, baseline_arm=args.baseline_arm
    )

    out_json = Path(args.out_json) if args.out_json else Path(f"results/arms/{args.product}.json")
    runner.save(output, out_json)
    print(f"✓ Saved arms comparison: {out_json}")

    out_md = Path(args.out_md) if args.out_md else Path(f"results/arms/{args.product}.md")
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(render_arms_report(output), encoding="utf-8")
    print(f"✓ Saved arms report:     {out_md}")

    if output.get("summary", {}).get("per_arm"):
        print("\nSummary (avg aggregate):")
        for arm, stats in output["summary"]["per_arm"].items():
            avg = stats.get("avg_aggregate")
            delta = stats.get("delta_vs_baseline")
            avg_s = "n/a" if avg is None else f"{avg:.1f}"
            delta_s = "" if (delta is None or arm == args.baseline_arm) else f" (Δ {delta:+.1f})"
            print(f"  {arm:<24} {avg_s}{delta_s}")


def register(sub, positive_int) -> None:
    """Add the `arms` subcommand group."""
    arms_p = sub.add_parser(
        "arms",
        help="Compare context-augmentation treatments (docs, MCP, skills, agent profiles)",
    )
    arms_sub = arms_p.add_subparsers(dest="arms_cmd", required=True)

    arms_run_p = arms_sub.add_parser(
        "run",
        help="Run an N-arm comparison and (optionally) judge it",
    )
    arms_run_p.add_argument("--product", required=True, help="Product name (e.g., oneTBB)")
    arms_run_p.add_argument("--questions", required=True, help="Path to questions JSON file")
    arms_run_p.add_argument(
        "--arms", required=True,
        help="Comma-separated arm specs. Examples: "
             "'baseline,docs', 'baseline,docs:local:./docs,profile:agent_profiles/concise_expert.md', "
             "'baseline,mcp:http=https://mcp.context7.com/mcp,skill:skills/onetbb-quickstart'",
    )
    arms_run_p.add_argument("--model", default="gpt-4o-mini", help="LLM for answering")
    arms_run_p.add_argument("--provider", default="openai",
                            choices=["openai", "anthropic", "amazon-bedrock", "google-vertex", "openrouter", "openai-codex"])
    arms_run_p.add_argument("--context7-id", default=None, dest="context7_id",
                            help="Explicit library id for doc/MCP arms (skips resolution)")
    arms_run_p.add_argument("--baseline-arm", default="baseline", dest="baseline_arm",
                            help="Arm name used as the delta baseline (default: baseline)")
    arms_run_p.add_argument("--judge", action="store_true",
                            help="Also score each arm with the LLM-as-judge")
    arms_run_p.add_argument("--judge-model", default="gpt-4o-mini", dest="judge_model")
    arms_run_p.add_argument("--judge-provider", default="openai", dest="judge_provider",
                            choices=["openai", "anthropic", "amazon-bedrock", "google-vertex", "openrouter", "openai-codex"])
    arms_run_p.add_argument("--top-k", type=positive_int, default=5, dest="top_k",
                            help="Docs to retrieve before reranking, for doc/MCP arms (default: 5)")
    arms_run_p.add_argument("--rerank-threshold", type=float, default=0.3, dest="rerank_threshold")
    arms_run_p.add_argument("--max-iterations", type=positive_int, default=6, dest="max_iterations",
                            help="Max tool-call rounds for agentic arms (agent:/skill-agent:, default: 6)")
    arms_run_p.add_argument("--concurrency", type=positive_int, default=5)
    arms_run_p.add_argument("--out-json", default=None, dest="out_json",
                            help="Output JSON path (default: results/arms/{product}.json)")
    arms_run_p.add_argument("--out-md", default=None, dest="out_md",
                            help="Output Markdown report path (default: results/arms/{product}.md)")
    arms_run_p.set_defaults(func=cmd_arms_run)
