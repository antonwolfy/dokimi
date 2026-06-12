"""Check the product and intent registries for drift.

Usage:
    python -m agent_benchmarks.config_check

Exits non-zero if ``config/products.yaml`` and ``products.yaml`` disagree on
the GitHub repo of any shared product, or if ``intents.yaml`` references a
product key that is not registered in ``products.yaml``. Intended for CI.
"""

from __future__ import annotations

import sys

from agent_benchmarks.config import detect_registry_drift
from agent_benchmarks.intents import IntentRegistry


def main() -> int:
    issues = detect_registry_drift()
    issues += IntentRegistry().validate()
    if issues:
        print("✗ registry drift detected:", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
        return 1
    print("✓ product and intent registries are consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
