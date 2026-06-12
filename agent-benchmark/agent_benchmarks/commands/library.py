"""library subcommand group: list, show."""

from __future__ import annotations

import argparse
import sys


def _load_registry(args):
    from agent_benchmarks.registry import LibraryRegistry
    from pathlib import Path as _Path
    reg_path = _Path(args.registry) if getattr(args, "registry", None) else None
    return LibraryRegistry(path=reg_path)


def cmd_library_list(args: argparse.Namespace) -> None:
    """List all libraries in the registry."""
    registry = _load_registry(args)
    entries = registry.list()
    if not entries:
        print("Registry is empty.")
        return
    print(f"{'Key':<12} {'Name':<16} {'Repo':<35} {'Doc sources'}")
    print("─" * 85)
    for e in entries:
        repo = e.repo or "—"
        sources = ", ".join(e.doc_sources)
        print(f"{e.key:<12} {e.name:<16} {repo:<35} {sources}")
    print(f"\n{len(entries)} libraries registered.")


def cmd_library_show(args: argparse.Namespace) -> None:
    """Show full details for a single library."""
    registry = _load_registry(args)
    try:
        entry = registry.get(args.name)
    except KeyError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"Key          : {entry.key}")
    print(f"Name         : {entry.name}")
    print(f"Repo         : {entry.repo or '—'}")
    print(f"Context7 ID  : {entry.context7_id or '—'}")
    print(f"Doc sources  : {', '.join(entry.doc_sources)}")
    print(f"Description  :\n  {entry.description}")


def register(sub, positive_int) -> None:
    """Add the `library` subcommand group."""
    library_p = sub.add_parser("library", help="Library registry management")
    library_sub = library_p.add_subparsers(dest="library_cmd", required=True)

    lib_list_p = library_sub.add_parser("list", help="List libraries in the registry")
    lib_list_p.add_argument("--registry", default=None, help="Path to custom libraries.yaml")
    lib_list_p.set_defaults(func=cmd_library_list)

    lib_show_p = library_sub.add_parser("show", help="Show details for a library")
    lib_show_p.add_argument("name", help="Library key (e.g., onetbb)")
    lib_show_p.add_argument("--registry", default=None, help="Path to custom libraries.yaml")
    lib_show_p.set_defaults(func=cmd_library_show)
