# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""repo subcommand group: repositories as evaluation subjects (repo_manifest.v1)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def cmd_repo_validate(args: argparse.Namespace) -> None:
    """Validate a repository's repo-eval.yaml and its tasks against one snapshot."""
    from agent_benchmarks.repos import (
        ManifestError,
        RepoSource,
        SourceError,
        check_repo,
        load_manifest,
        open_source,
    )

    from agent_benchmarks.repos.source import base_opener

    try:
        source = RepoSource.parse(args.source)
        tree = open_source(source, _cache_dir(args))
        manifest = load_manifest(tree, args.manifest)
    except (SourceError, ManifestError) as exc:
        print(f"✗ {exc}", file=sys.stderr)
        sys.exit(1)
    open_base = base_opener(source, tree)
    report = check_repo(tree, manifest, open_base)
    if open_base is None:
        report.notes.append("task bases were not checked: the source has no git history")

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        mark = "✓" if report.ok else "✗"
        families = ", ".join(f"{k} {v}" for k, v in report.to_dict()["tasks"]["by_family"].items())
        print(f"{mark} {manifest.id}: {manifest.path} in {report.tree}")
        print(f"  tasks: {len(report.tasks)} ({families or 'none valid'})")
        line = f"  guidance files: {len(report.guidance_files)} at the eval tree"
        if report.guidance_by_base:
            counts = report.guidance_by_base.values()
            line += f"; {min(counts)}–{max(counts)} across {len(counts)} task bases"
        print(line)
        for warning in report.warnings:
            print(f"  warning: {warning}")
        for note in report.notes:
            print(f"  note: {note}")
        for error in report.errors:
            print(f"  error: {error}", file=sys.stderr)
    if not report.ok:
        sys.exit(1)


def cmd_repo_fetch(args: argparse.Namespace) -> None:
    """Clone (once) and fetch a pinned remote source into the cache; print the SHA."""
    from agent_benchmarks.repos import RepoSource, SourceError, open_source
    from agent_benchmarks.repos.source import GitTree

    try:
        source = RepoSource.parse(args.source)
        if source.rev is None:
            raise SourceError("fetch needs a pinned source: <url-or-path>@<rev>")
        tree = open_source(source, _cache_dir(args))
    except SourceError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        sys.exit(1)
    assert isinstance(tree, GitTree)
    print(f"{tree.sha}\t{tree.git_dir}")


def _cache_dir(args: argparse.Namespace) -> Path | None:
    return Path(args.cache_dir) if args.cache_dir else None


def register(sub, positive_int) -> None:
    """Add the `repo` subcommand group."""
    repo_p = sub.add_parser(
        "repo",
        help="Repositories as evaluation subjects: validate repo-eval.yaml, fetch sources",
    )
    repo_sub = repo_p.add_subparsers(dest="repo_cmd", required=True)
    source_help = (
        "Repository source: a local directory (read as it is), <dir>@<rev>, or "
        "<https-or-ssh-url>@<rev> (cloned bare into the cache)"
    )
    cache_help = "Clone cache directory (default: $AGENT_BENCHMARK_REPO_CACHE or ~/.cache/agent-benchmark/repos)"

    validate_p = repo_sub.add_parser(
        "validate", help="Validate the manifest and every task.json against one snapshot"
    )
    validate_p.add_argument("source", help=source_help)
    validate_p.add_argument(
        "--manifest",
        default=".agent-eval/repo-eval.yaml",
        help="Manifest path relative to the repository root (default: .agent-eval/repo-eval.yaml)",
    )
    validate_p.add_argument("--cache-dir", default=None, dest="cache_dir", help=cache_help)
    validate_p.add_argument("--json", action="store_true", help="Print the full report as JSON")
    validate_p.set_defaults(func=cmd_repo_validate)

    fetch_p = repo_sub.add_parser("fetch", help="Clone/fetch a pinned source and print its commit SHA")
    fetch_p.add_argument("source", help=source_help)
    fetch_p.add_argument("--cache-dir", default=None, dest="cache_dir", help=cache_help)
    fetch_p.set_defaults(func=cmd_repo_fetch)
