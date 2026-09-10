"""Check the product and intent registries for drift.

Usage:
    python -m agent_benchmarks.config_check
    python -m agent_benchmarks.config_check --tasks-root <dir> --questions-root <dir>

Exits non-zero if ``config/products.yaml`` and ``products.yaml`` disagree on
the GitHub repo of any shared product, or if ``intents.yaml`` references a
product key that is not registered in ``products.yaml``, or if a product's
coverage declaration is broken (``coverage_status: covered`` with no
resolvable task/question set, or a declared questions file that is absent).

The coverage half is checked against ``--tasks-root`` (task dirs with a
``task.toml``) and ``--questions-root`` (``<product_key>_golden.json`` files)
when they are given — those roots hold evaluation content and live outside this
repository. Without them the coverage check is limited to declaration validity.
Intended for CI.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from agent_benchmarks.config import detect_registry_drift
from agent_benchmarks.coverage import coverage_issues
from agent_benchmarks.intents import IntentRegistry


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m agent_benchmarks.config_check",
        description="Check the product and intent registries for drift.",
    )
    parser.add_argument(
        "--tasks-root",
        default=None,
        help="Directory of executable task dirs (each with task.toml) used to "
             "resolve the work half of the coverage contract, e.g. "
             "/path/to/content-repo/evaluation/harbor/tasks",
    )
    parser.add_argument(
        "--questions-root",
        default=None,
        help="Directory holding <product_key>_golden.json question sets used to "
             "resolve the awareness half, e.g. /path/to/content-repo/questions",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or [])
    issues = detect_registry_drift()
    issues += IntentRegistry().validate()
    issues += coverage_issues(
        tasks_dir=Path(args.tasks_root) if args.tasks_root else None,
        questions_dir=Path(args.questions_root) if args.questions_root else None,
    )
    if issues:
        print("✗ registry drift detected:", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
        return 1
    print("✓ product and intent registries are consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
