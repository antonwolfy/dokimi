# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""catalog subcommand group: scan external skill/task catalogs before use.

Points at a local checkout the caller already produced (e.g.
``git clone https://github.com/uxlfoundation/skills``) -- nothing here
fetches anything over the network. See ``agent_benchmarks.external.catalog``
for the manifest formats understood.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def cmd_catalog_scan(args: argparse.Namespace) -> None:
    from agent_benchmarks.external import read_skill_manifest, read_task_manifest

    root = Path(args.root)
    if not root.is_dir():
        raise SystemExit(f"--root is not a directory: {root}")

    any_failure = False

    if args.kind in ("skills", "all"):
        try:
            entries = read_skill_manifest(root)
        except ValueError as exc:
            raise SystemExit(f"skills.yaml: {exc}") from exc
        print(f"# skills ({len(entries)} declared under {root})")
        for entry in entries:
            state = "ok" if entry.loaded else f"ERROR: {entry.error}"
            status = entry.status or "-"
            print(f"{entry.name}\t{status}\t{entry.path}\t{state}")
            if not entry.loaded:
                any_failure = True
        print()

    if args.kind in ("tasks", "all"):
        try:
            entries = read_task_manifest(root, tasks_subdir=args.tasks_subdir)
        except ValueError as exc:
            raise SystemExit(f"suites.json: {exc}") from exc
        print(f"# tasks ({len(entries)} declared under {root})")
        for entry in entries:
            if entry.loaded:
                state = "ok"
            elif entry.skipped:
                state = f"skipped: {entry.reason}"
            else:
                state = f"ERROR: {entry.reason}"
                any_failure = True
            track = entry.track or "-"
            status = entry.status or "-"
            print(f"{entry.name}\t{status}\t{track}\t{state}")

    if any_failure:
        raise SystemExit(1)


def register(sub, positive_int) -> None:
    """Add the `catalog` subcommand group."""

    catalog_p = sub.add_parser(
        "catalog",
        help="Scan an external skill/task catalog (e.g. a local uxlfoundation/skills checkout)",
    )
    catalog_sub = catalog_p.add_subparsers(dest="catalog_cmd", required=True)

    scan_p = catalog_sub.add_parser(
        "scan", help="Report which skills/tasks under --root load cleanly"
    )
    scan_p.add_argument("--root", required=True, help="Local checkout to scan")
    scan_p.add_argument(
        "--kind", choices=["skills", "tasks", "all"], default="all",
        help="Restrict the scan to skills, tasks, or both (default: all)",
    )
    scan_p.add_argument(
        "--tasks-subdir", default="evaluation/harbor/tasks",
        help="Task directory relative to --root (default: evaluation/harbor/tasks, "
             "the uxlfoundation/skills convention)",
    )
    scan_p.set_defaults(func=cmd_catalog_scan)
