#!/usr/bin/env python3
"""
Combined multi-model comparison script that handles regular AND golden questions.

Usage:
    # Compare models on regular questions only
    python scripts/compare_models_combined.py \
        --regular-runs results/arms/dpnp_regular_sonnet46.json results/arms/dpnp_regular_opus48.json \
        --run-ids sonnet46,opus48 \
        --out results/dpnp_compare.md

    # Compare models on golden questions only
    python scripts/compare_models_combined.py \
        --golden-runs results/arms/dpnp_golden_sonnet46.json results/arms/dpnp_golden_opus48.json \
        --run-ids sonnet46,opus48 \
        --out results/dpnp_compare.md

    # Compare models on BOTH regular AND golden questions
    python scripts/compare_models_combined.py \
        --regular-runs results/arms/dpnp_regular_sonnet46.json results/arms/dpnp_regular_opus48.json \
        --golden-runs results/arms/dpnp_golden_sonnet46.json results/arms/dpnp_golden_opus48.json \
        --run-ids sonnet46,opus48 \
        --out results/dpnp_compare.md
"""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).resolve().parent
COMPARE_MODELS_SCRIPT = SCRIPT_DIR / "compare_models.py"

try:
    from zoneinfo import ZoneInfo

    _TZ = ZoneInfo("America/Los_Angeles")
except ImportError:
    _TZ = None


def run_compare_models(runs: list[str], run_ids: str, temp_out: Path, run_type: str) -> str:
    """Run compare_models.py and return markdown content."""
    if run_type not in {"regular", "golden"}:
        raise ValueError(f"Unknown run type: {run_type}")
    run_flag = "--regular-runs" if run_type == "regular" else "--golden-runs"
    cmd = [sys.executable, str(COMPARE_MODELS_SCRIPT), run_flag] + runs + [
        "--run-ids", run_ids, "--out", str(temp_out)
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")

    if result.returncode != 0:
        raise RuntimeError(
            f"compare_models.py failed for {run_type} runs with exit code {result.returncode}:\n"
            f"{result.stderr.strip()}"
        )

    return temp_out.read_text(encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(
        description="Compare multiple model runs on regular and/or golden questions"
    )
    parser.add_argument(
        "--regular-runs", nargs="+", help="Paths to regular questions judged JSON files"
    )
    parser.add_argument(
        "--golden-runs", nargs="+", help="Paths to golden questions judged JSON files"
    )
    parser.add_argument(
        "--run-ids", required=True, help="Comma-separated run IDs (e.g., sonnet46,opus48)"
    )
    parser.add_argument("--out", required=True, help="Output markdown file path")

    args = parser.parse_args()

    # Validate: at least one of regular-runs or golden-runs must be provided
    if not args.regular_runs and not args.golden_runs:
        print("Error: Must provide at least --regular-runs or --golden-runs", file=sys.stderr)
        return 1

    run_ids = [rid.strip() for rid in args.run_ids.split(",")]

    # Validate run counts
    if args.regular_runs and len(args.regular_runs) != len(run_ids):
        print(
            f"Error: Number of regular runs ({len(args.regular_runs)}) must match number of run IDs ({len(run_ids)})",
            file=sys.stderr,
        )
        return 1

    if args.golden_runs and len(args.golden_runs) != len(run_ids):
        print(
            f"Error: Number of golden runs ({len(args.golden_runs)}) must match number of run IDs ({len(run_ids)})",
            file=sys.stderr,
        )
        return 1

    lines = []

    # Header
    lines += [
        "#  Model Comparison Report",
        f"_Generated: {datetime.now(tz=_TZ).strftime('%Y-%m-%d %H:%M %Z') if _TZ else datetime.now().strftime('%Y-%m-%d %H:%M UTC')}_",
        "",
    ]

    # If both regular and golden, add overview
    if args.regular_runs and args.golden_runs:
        lines += [
            "## Overview",
            "",
            "This report compares models across two question sets:",
            "- **Regular Questions**: 12 standard questions covering getting started, compatibility, performance, and troubleshooting",
            "- **Golden Questions**: 7 scenario-based questions derived from real GitHub issues",
            "",
        ]

    # Generate regular section
    if args.regular_runs:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as tmp:
            temp_path = Path(tmp.name)

        print("Generating regular questions analysis...")
        try:
            regular_content = run_compare_models(
                args.regular_runs, args.run_ids, temp_path, "regular"
            )
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        finally:
            temp_path.unlink(missing_ok=True)

        # Skip header from sub-report
        regular_lines = regular_content.split("\n")
        # Find where content starts (after first "##")
        start_idx = 0
        for i, line in enumerate(regular_lines):
            if line.strip().startswith("##") and "Models Compared" in line:
                start_idx = i
                break

        if args.regular_runs and args.golden_runs:
            lines += [
                "---",
                "",
                "# Regular Questions Analysis",
                "",
            ]

        lines += regular_lines[start_idx:]

    # Generate golden section
    if args.golden_runs:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as tmp:
            temp_path = Path(tmp.name)

        print("Generating golden questions analysis...")
        try:
            golden_content = run_compare_models(args.golden_runs, args.run_ids, temp_path, "golden")
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        finally:
            temp_path.unlink(missing_ok=True)

        # Skip header from sub-report
        golden_lines = golden_content.split("\n")
        start_idx = 0
        for i, line in enumerate(golden_lines):
            if line.strip().startswith("##") and "Models Compared" in line:
                start_idx = i
                break

        if args.regular_runs and args.golden_runs:
            lines += [
                "",
                "---",
                "",
                "# Golden Questions Analysis",
                "",
            ]

        lines += golden_lines[start_idx:]

    # Write final output
    output = "\n".join(lines)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(output, encoding="utf-8")
    print(f"✅ Combined report written to {args.out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
