"""report subcommand group: eval, generate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from doc_benchmarks.report.markdown_report import write_compare_report, write_run_report


def cmd_report(args: argparse.Namespace) -> None:
    """Generate markdown report from JSON snapshot."""
    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    out_md = Path(args.out_md).resolve()

    if "diff" in data:
        write_compare_report(data, out_md)
    else:
        write_run_report(data, out_md)


def cmd_report_eval(args: argparse.Namespace) -> None:
    """Generate quality report from eval JSON (dynamic vs static breakdown)."""
    from doc_benchmarks.report.eval_report import generate_report

    if args.out:
        out = args.out
    elif getattr(args, "run_id", None):
        out = f"results/{args.product.lower()}_{args.run_id}/reports/{args.product}_full.md"
    else:
        out = f"results/{args.product}/reports/{args.product}_full.md"
    generate_report(eval_path=args.eval, out_path=out)


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


def register(sub, positive_int) -> None:
    """Add the `report` subcommand group."""
    report_p = sub.add_parser("report", help="Generate analysis reports")
    report_sub = report_p.add_subparsers(dest="report_cmd", required=True)

    # report eval — lightweight, no questions needed
    eval_r_p = report_sub.add_parser("eval", help="Generate quality report from eval JSON (dynamic vs static breakdown)")
    eval_r_p.add_argument("--product", required=True, help="Product name (e.g., oneDAL)")
    eval_r_p.add_argument("--eval", required=True, help="Path to eval JSON file")
    eval_r_p.add_argument("--run-id", default=None, dest="run_id",
                         help="Run tag (e.g. gpt4o). Auto-sets output path.")
    eval_r_p.add_argument("--out", default=None, help="Output .md file (default: results/{product}/reports/{product}_full.md)")
    eval_r_p.set_defaults(func=cmd_report_eval)

    # report generate
    gen_r_p = report_sub.add_parser("generate", help="Generate comprehensive report from eval results")
    gen_r_p.add_argument("--product", required=True, help="Product name (e.g., oneTBB)")
    gen_r_p.add_argument("--eval", required=True, help="Path to eval JSON file")
    gen_r_p.add_argument("--questions", required=True, help="Path to questions JSON file")
    gen_r_p.add_argument("--output", default=None, help="Output file (default: reports/{product}.md)")
    gen_r_p.add_argument("--format", default="markdown", choices=["markdown", "json"], help="Output format")
    gen_r_p.set_defaults(func=cmd_report_generate)
