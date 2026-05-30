"""Check the two product registries for identity drift.

Usage:
    python -m doc_benchmarks.config_check

Exits non-zero if ``config/products.yaml`` and ``libraries.yaml`` disagree on
the GitHub repo of any shared product. Intended for CI.
"""

from __future__ import annotations

import sys

from doc_benchmarks.config import detect_registry_drift


def main() -> int:
    issues = detect_registry_drift()
    if issues:
        print("✗ product registry drift detected:", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
        return 1
    print("✓ product registries are consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
