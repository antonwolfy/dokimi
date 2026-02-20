#!/usr/bin/env python3
"""CLI for doc-benchmark: run, compare, report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

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

    cmp_p = sub.add_parser("compare")
    cmp_p.add_argument("--base", required=True)
    cmp_p.add_argument("--candidate", required=True)
    cmp_p.add_argument("--spec", default=None, help="Spec file for regression thresholds")
    cmp_p.add_argument("--out-json", default="reports/compare.json")
    cmp_p.add_argument("--out-md", default="reports/compare.md")
    cmp_p.set_defaults(func=cmd_compare)

    rep_p = sub.add_parser("report")
    rep_p.add_argument("--input", required=True)
    rep_p.add_argument("--out-md", default="reports/report.md")
    rep_p.set_defaults(func=cmd_report)

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

    return p


def main() -> None:
    """Entry point."""
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
