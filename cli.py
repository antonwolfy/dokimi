#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from doc_benchmarks.report.json_report import write_json
from doc_benchmarks.report.markdown_report import write_compare_report, write_run_report
from doc_benchmarks.runner.compare import compare_snapshots
from doc_benchmarks.runner.run import run_benchmark, save_snapshot


def cmd_run(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    spec = Path(args.spec).resolve()
    out_json = Path(args.out_json).resolve()
    out_md = Path(args.out_md).resolve()

    result = run_benchmark(root, spec)
    save_snapshot(result, out_json)
    write_run_report(result, out_md)
    print(json.dumps(result["summary"], indent=2))


def cmd_compare(args: argparse.Namespace) -> None:
    base = Path(args.base).resolve()
    cand = Path(args.candidate).resolve()
    out_json = Path(args.out_json).resolve()
    out_md = Path(args.out_md).resolve()

    result = compare_snapshots(base, cand)
    write_json(result, out_json)
    write_compare_report(result, out_md)
    print(json.dumps(result["diff"], indent=2))


def cmd_report(args: argparse.Namespace) -> None:
    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    out_md = Path(args.out_md).resolve()

    if "diff" in data:
        write_compare_report(data, out_md)
    else:
        write_run_report(data, out_md)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="doc-benchmark-cli")
    sub = p.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run")
    run_p.add_argument("--root", default=".")
    run_p.add_argument("--spec", default="benchmarks/spec.v1.yaml")
    run_p.add_argument("--out-json", default="baselines/current.json")
    run_p.add_argument("--out-md", default="reports/current.md")
    run_p.set_defaults(func=cmd_run)

    cmp_p = sub.add_parser("compare")
    cmp_p.add_argument("--base", required=True)
    cmp_p.add_argument("--candidate", required=True)
    cmp_p.add_argument("--out-json", default="reports/compare.json")
    cmp_p.add_argument("--out-md", default="reports/compare.md")
    cmp_p.set_defaults(func=cmd_compare)

    rep_p = sub.add_parser("report")
    rep_p.add_argument("--input", required=True)
    rep_p.add_argument("--out-md", default="reports/report.md")
    rep_p.set_defaults(func=cmd_report)

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
