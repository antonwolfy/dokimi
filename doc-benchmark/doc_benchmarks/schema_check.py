"""Validate the benchmark spec against its JSON Schema.

Usage:
    python -m doc_benchmarks.schema_check [spec_path ...]

Defaults to ``benchmarks/spec.v1.yaml``. Exits non-zero on the first invalid
spec, printing human-readable errors. Intended for use in CI and pre-commit.
"""

from __future__ import annotations

import sys
from pathlib import Path

from doc_benchmarks.runner.spec import SpecValidationError, load_spec

DEFAULT_SPECS = ["benchmarks/spec.v1.yaml"]


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    specs = argv or DEFAULT_SPECS

    failures = 0
    for spec in specs:
        path = Path(spec)
        try:
            load_spec(path)
        except (SpecValidationError, RuntimeError) as exc:
            failures += 1
            print(f"✗ {path}\n{exc}", file=sys.stderr)
        else:
            print(f"✓ {path}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
