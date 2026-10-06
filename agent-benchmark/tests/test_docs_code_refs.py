# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""The commands, flags, files and modules the docs name exist.

A doc that tells the reader to run a subcommand that was renamed, pass a flag that was
dropped, or open a file that moved is wrong in a way no reader can repair alone. The CLI
is the source of truth for commands and flags; the tree is the source of truth for paths.
Only code -- fenced blocks and inline code spans -- is checked, so prose that happens to
contain "agent-benchmark" is not mistaken for a command.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import re
import shlex
from pathlib import Path

import pytest

from agent_benchmarks.cli import build_parser

PROJECT = Path(__file__).resolve().parents[1]
DOCS = [
    *sorted((PROJECT / "docs").glob("*.md")),
    PROJECT / "README.md",
    PROJECT / "CONTRIBUTING.md",
    PROJECT.parent / "README.md",
    PROJECT.parent / "CLAUDE.md",
]
DOCS = [d for d in DOCS if d.exists()]

FENCE = re.compile(r"^```[^\n]*\n(.*?)^```", re.M | re.S)
SPAN = re.compile(r"`([^`\n]+)`")
# `python cli.py ...`, `python -m agent_benchmarks ...`, `agent-benchmark ...`
COMMAND = re.compile(
    r"(?:python3?\s+(?:-m\s+agent_benchmarks\b|\S*cli\.py)|(?<![\w/.-])agent-benchmark(?![\w/.-]))"
    r"\s+(.*)"
)
# Repo paths a reader is told to open. tests/ only as test modules: task-content docs
# talk about a task's own tests/ directory, which is not this repo's.
PATH = re.compile(r"^(?:(?:agent_benchmarks|benchmarks|scripts|config)/[\w./-]+|tests/test_\w+\.py)$")
MODULE = re.compile(r"^agent_benchmarks(?:\.\w+)+$")
# `python -m agent_benchmarks.config_check ...`: the module a command runs.
RUN_MODULE = re.compile(r"python3?\s+-m\s+(agent_benchmarks(?:\.\w+)+)")
PLACEHOLDER = re.compile(r"[<>\[\]{}…*$]|\.\.\.")


def _code(text: str) -> list[str]:
    """Code lines: fenced blocks (continuations joined) and inline spans."""
    blocks = [re.sub(r"\s*\\\n\s*", " ", b) for b in FENCE.findall(text)]
    prose = FENCE.sub("", text)
    return [line for b in blocks for line in b.splitlines()] + SPAN.findall(prose)


def _subcommands(parser: argparse.ArgumentParser) -> dict:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action.choices
    return {}


def _flags(parser: argparse.ArgumentParser) -> set[str]:
    return {opt for action in parser._actions for opt in action.option_strings}


def _check_command(args: str) -> list[str]:
    try:
        tokens = shlex.split(re.split(r"\s(?:\||&&|;|#|>)", args)[0])
    except ValueError:
        return []
    parser, path, problems = build_parser(), [], []
    for token in tokens:
        subs = _subcommands(parser)
        if subs and not token.startswith("-"):
            if token in subs:
                parser = subs[token]
                path.append(token)
                continue
            if re.fullmatch(r"[a-z][a-z0-9-]*", token):
                problems.append(f"unknown command: {' '.join([*path, token])}")
            break
        if token.startswith("--") and not PLACEHOLDER.search(token):
            flag = token.split("=", 1)[0]
            if flag not in _flags(parser):
                problems.append(f"unknown flag: {' '.join(path)} {flag}")
    return problems


def _module_exists(dotted: str) -> bool:
    # The module itself, or an attribute of its parent module (`pkg.mod.func`). Resolved by
    # import: a file-existence test of the parent accepts any name under any package.
    try:
        if importlib.util.find_spec(dotted) is not None:
            return True
    except ImportError:
        pass
    parent, _, name = dotted.rpartition(".")
    try:
        return hasattr(importlib.import_module(parent), name)
    except ImportError:
        return False


def _problems(doc: Path) -> list[str]:
    found = []
    for code in _code(doc.read_text(encoding="utf-8")):
        # A shell comment is prose: `make test  # runs the agent-benchmark suite`.
        for match in COMMAND.finditer(re.split(r"(?:^|\s)#", code, maxsplit=1)[0]):
            found += _check_command(match.group(1))
        ref = code.strip()
        if PATH.match(ref) and not PLACEHOLDER.search(ref) and not (PROJECT / ref).exists():
            found.append(f"missing path: {ref}")
        if MODULE.match(ref) and not _module_exists(ref):
            found.append(f"missing module: {ref}")
        for run in RUN_MODULE.findall(code):
            try:
                runnable = importlib.util.find_spec(run) is not None
            except ImportError:
                runnable = False
            if not runnable:
                found.append(f"missing module: {run}")
    return sorted(set(found))


@pytest.mark.parametrize("doc", DOCS, ids=lambda d: str(d.relative_to(PROJECT.parent)))
def test_doc_code_references_resolve(doc):
    assert _problems(doc) == []


def test_the_checker_sees_commands_flags_and_paths():
    assert _check_command("tasks run --tasks x --harnesses docker-oracle") == []
    assert _check_command("tasks sprint") == ["unknown command: tasks sprint"]
    assert _check_command("tasks run --no-such-flag") == ["unknown flag: tasks run --no-such-flag"]
    assert _check_command("tasks run --tasks <id> | tee log") == []
    assert _code("x `agent_benchmarks/cli.py` y\n```bash\npython cli.py tasks \\\n  run\n```\n") == [
        "python cli.py tasks run", "agent_benchmarks/cli.py"]


def test_the_checker_resolves_modules():
    assert _module_exists("agent_benchmarks.eval.stats.mean_ci")
    assert not _module_exists("agent_benchmarks.eval.nope")
    assert not _module_exists("agent_benchmarks.config_chek")


def test_the_checker_resolves_python_m_modules(tmp_path):
    doc = tmp_path / "x.md"
    doc.write_text("```bash\npython -m agent_benchmarks.config_chek --x\n"
                   "python -m agent_benchmarks.nope.deeper\npython -m agent_benchmarks.config_check\n```\n")
    assert _problems(doc) == ["missing module: agent_benchmarks.config_chek",
                              "missing module: agent_benchmarks.nope.deeper"]
