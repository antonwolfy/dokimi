# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Executable task discovery and metadata loading.

Two on-disk layouts are understood and normalised into one :class:`TaskSpec`:

``harbor``
    The split Harbor/terminal-bench layout: ``task.toml`` + ``instruction.md``,
    with ``solution/solve.sh`` and ``tests/test.sh``.
``task-md``
    The BenchFlow unified layout used by SkillsBench: a single ``task.md``
    whose YAML frontmatter carries the same tables (``metadata``, ``verifier``,
    ``agent``, and ``sandbox`` — called ``environment`` before schema 1.3) and
    whose body (its ``## prompt`` section, when it has one) is the instruction,
    with ``oracle/solve.sh`` and ``verifier/test.sh``.

A directory holding both is loaded as ``task-md`` (the format BenchFlow treats
as canonical when it migrates a split task) when the ``task.md`` frontmatter
has a BenchFlow key; any other ``task.md`` there is an author's note and the
task loads from ``task.toml``.
"""

from __future__ import annotations

import datetime
import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    import tomli as tomllib  # type: ignore[no-redef]


# Executable tasks live in a separate evaluation-content checkout, so there is
# no in-repo default root: the caller always names one.
NO_TASKS_ROOT_MESSAGE = (
    "no tasks root given; pass --tasks-root <checkout>/evaluation/harbor/tasks "
    "(or a full path to a single task directory)"
)

FORMAT_HARBOR = "harbor"
FORMAT_TASK_MD = "task-md"

# Where each layout keeps its oracle and its verifier, in lookup order. Both
# names are tried for either format, as BenchFlow accepts both. The order
# differs from BenchFlow's in one case: BenchFlow always prefers oracle/ and
# verifier/, while a Harbor-layout directory that holds both pairs uses
# solution/ and tests/ here, the names Harbor itself reads.
_SOLUTION_DIRS = {FORMAT_HARBOR: ("solution", "oracle"), FORMAT_TASK_MD: ("oracle", "solution")}
_TESTS_DIRS = {FORMAT_HARBOR: ("tests", "verifier"), FORMAT_TASK_MD: ("verifier", "tests")}


@dataclass(frozen=True)
class TaskSpec:
    """Resolved executable task descriptor, whichever layout it came from."""

    name: str
    path: Path
    instruction: str
    metadata: dict[str, Any] = field(default_factory=dict)
    verifier: dict[str, Any] = field(default_factory=dict)
    agent: dict[str, Any] = field(default_factory=dict)
    environment: dict[str, Any] = field(default_factory=dict)
    oracle: dict[str, Any] = field(default_factory=dict)
    format: str = FORMAT_HARBOR
    schema_version: str | None = None

    @property
    def timeout_sec(self) -> float | None:
        value = self.agent.get("timeout_sec")
        return float(value) if value is not None else None

    @property
    def solution_dir(self) -> Path:
        return _first_dir(self.path, _SOLUTION_DIRS[self.format])

    @property
    def tests_dir(self) -> Path:
        return _first_dir(self.path, _TESTS_DIRS[self.format])

    @property
    def skills_dir(self) -> Path | None:
        """Task-bundled skills (``environment/skills``), if the task ships any."""
        path = self.path / "environment" / "skills"
        return path if path.is_dir() else None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": str(self.path),
            "format": self.format,
            "schema_version": self.schema_version,
            "metadata": self.metadata,
            "verifier": self.verifier,
            "agent": self.agent,
            "environment": self.environment,
            "oracle": self.oracle,
        }


def task_format(path: Path) -> str | None:
    """The layout of the task directory at *path*, or ``None`` if it is not one."""

    path = Path(path)
    has_toml = (path / "task.toml").is_file()
    if (path / "task.md").is_file():
        # Next to a task.toml, a task.md is a BenchFlow task only if its
        # frontmatter is a mapping with a BenchFlow key. Anything else (no
        # frontmatter, Jekyll/Hugo frontmatter, a leading horizontal rule, an
        # unclosed block) is an author's note: the directory loads from
        # task.toml, as it did before task.md was read at all.
        if not has_toml or _is_benchflow_task_md(path / "task.md"):
            return FORMAT_TASK_MD
    if has_toml:
        return FORMAT_HARBOR
    return None


def _has_frontmatter(path: Path) -> bool:
    with path.open(encoding="utf-8", errors="replace") as fh:
        return fh.readline().strip() == "---"


# Top-level keys of a BenchFlow task.md (TaskConfig), plus the pre-1.3
# 'environment' spelling of 'sandbox' that load_task also accepts.
_BENCHFLOW_KEYS = frozenset(
    {"schema_version", "metadata", "verifier", "agent", "sandbox", "environment", "oracle"}
)

# task_format runs several times per directory (discovery, load_task,
# read_task_config); warn about each ignored file once per process.
_WARNED: set[str] = set()


def _warn_once(message: str) -> None:
    if message not in _WARNED:
        _WARNED.add(message)
        warnings.warn(message, stacklevel=3)


def _is_benchflow_task_md(path: Path) -> bool:
    """Whether a ``task.md`` next to a ``task.toml`` is the task (see task_format)."""
    if not _has_frontmatter(path):
        return False  # plain notes: nothing to say
    try:
        data = _split_frontmatter(path)[0]
    except ValueError as exc:
        _warn_once(f"ignoring task.md next to task.toml, loading task.toml: {exc}")
        return False
    if _BENCHFLOW_KEYS & data.keys():
        return True
    _warn_once(
        f"ignoring task.md next to task.toml, loading task.toml: its frontmatter has "
        f"no BenchFlow key ({', '.join(sorted(_BENCHFLOW_KEYS))}): {path}"
    )
    return False


def is_task_dir(path: Path) -> bool:
    return task_format(path) is not None


def discover_tasks(root: Path | None = None) -> list[TaskSpec]:
    """Load every task directory under *root* (either layout).

    Args:
        root: tasks root to scan. Required — there is no bundled task tree.

    Raises:
        ValueError: if *root* is None.
    """

    if root is None:
        raise ValueError(NO_TASKS_ROOT_MESSAGE)
    root = Path(root)
    if not root.is_dir():
        return []
    tasks = []
    for path in sorted(root.iterdir()):
        fmt = task_format(path)
        if fmt is None:
            continue
        if fmt == FORMAT_TASK_MD and not _has_frontmatter(path / "task.md"):
            # A lone task.md without frontmatter (planning notes, say) is not
            # a task. BenchFlow's batch discovery skips it too; load_task on
            # that directory still raises.
            _warn_once(f"skipping {path}: task.md has no YAML frontmatter")
            continue
        tasks.append(load_task(path))
    return tasks


def load_task(path_or_name: str | Path, root: Path | None = None) -> TaskSpec:
    """Load one task by directory path, or by task name relative to *root*.

    A full path is loaded without a *root*; a bare task name needs one.
    """

    path = Path(path_or_name)
    if not path.exists():
        if root is None:
            # A bare task name cannot be resolved without a root; a path that
            # was spelled out is simply missing.
            if not path.is_absolute() and len(path.parts) == 1:
                raise ValueError(NO_TASKS_ROOT_MESSAGE)
            raise FileNotFoundError(f"Task directory not found: {path_or_name}")
        path = Path(root) / str(path_or_name)
    path = path.resolve()
    if not path.is_dir():
        raise FileNotFoundError(f"Task directory not found: {path_or_name}")

    fmt = task_format(path)
    if fmt == FORMAT_TASK_MD:
        data, instruction = _read_task_md(path / "task.md")
    elif fmt == FORMAT_HARBOR:
        instruction_path = path / "instruction.md"
        if not instruction_path.is_file():
            raise FileNotFoundError(f"Task has no instruction.md: {path}")
        data = read_task_config(path)
        instruction = instruction_path.read_text(encoding="utf-8")
    else:
        raise FileNotFoundError(f"Task has no task.toml or task.md: {path}")

    # BenchFlow schema 1.3 renamed [environment] to [sandbox]; either feeds
    # TaskSpec.environment. BenchFlow rejects 'environment:' inside a task.md;
    # it is accepted here so SkillsBench snapshots written before the rename
    # still load. Declaring both is rejected, as BenchFlow does:
    # they are one section, and a silent merge would accept a file BenchFlow
    # refuses to run.
    if isinstance(data.get("environment"), dict) and isinstance(data.get("sandbox"), dict):
        raise ValueError(
            f"task declares both 'environment' and 'sandbox' (the same section; "
            f"'environment' is the legacy Harbor spelling); keep only 'sandbox': {path}"
        )
    environment = _table(data.get("sandbox")) or _table(data.get("environment"))
    version = data.get("schema_version")
    return TaskSpec(
        name=path.name,
        path=path,
        instruction=instruction,
        metadata=_table(data.get("metadata")),
        verifier=_table(data.get("verifier")),
        agent=_table(data.get("agent")),
        environment=environment,
        oracle=_table(data.get("oracle")),
        format=fmt,
        schema_version=str(version) if version is not None else None,
    )


def read_task_config(path: Path) -> dict[str, Any]:
    """The raw config tables of a task directory, without the instruction.

    For scanners that only need metadata: unlike :func:`load_task` it does not
    require ``instruction.md``. Raises ``ValueError`` on an unparsable file and
    ``FileNotFoundError`` when *path* holds neither layout.
    """

    path = Path(path)
    fmt = task_format(path)
    if fmt == FORMAT_TASK_MD:
        return _read_task_md(path / "task.md")[0]
    if fmt == FORMAT_HARBOR:
        try:
            return _plain(tomllib.loads((path / "task.toml").read_text(encoding="utf-8")))
        except tomllib.TOMLDecodeError as exc:
            raise ValueError(f"task.toml is not valid TOML: {path}: {exc}") from exc
    raise FileNotFoundError(f"Task has no task.toml or task.md: {path}")


def _read_task_md(path: Path) -> tuple[dict[str, Any], str]:
    """Split a ``task.md`` into its YAML frontmatter and its instruction body."""

    data, body = _split_frontmatter(path)
    _reject_authoring_shorthands(data, path)
    return _plain(data), _prompt_section(body, path)


def _split_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    """A ``task.md``'s frontmatter mapping and its raw body; ``ValueError`` if malformed."""

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"task.md has no YAML frontmatter: {path}")
    for end in range(1, len(lines)):
        if lines[end].strip() == "---":
            break
    else:
        raise ValueError(f"task.md frontmatter is not closed with '---': {path}")
    try:
        data = yaml.safe_load("".join(lines[1:end])) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"task.md frontmatter is not valid YAML: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"task.md frontmatter must be a mapping: {path}")
    return data, "".join(lines[end + 1:]).lstrip("\n")


# BenchFlow's reserved body headings (benchflow.task._document_parse). Only
# ``## prompt`` (or, without it, the text before the first heading) is the
# agent's instruction; role, scene and user-persona sections are for other
# participants and must not reach the solver.
_SECTION_RE = re.compile(
    r"^##\s+(prompt|role:[A-Za-z0-9_.-]+|scene:[A-Za-z0-9_.-]+|user-persona)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_ESCAPED_SECTION_RE = re.compile(
    r"^\\(##\s+(?:prompt|role:[A-Za-z0-9_.-]+|scene:[A-Za-z0-9_.-]+|user-persona)\s*)$",
    re.IGNORECASE | re.MULTILINE,
)


def _prompt_section(body: str, path: Path) -> str:
    """The instruction BenchFlow would give the agent for this body."""

    matches = list(_SECTION_RE.finditer(body))
    if not matches:
        return body.strip()  # BenchFlow strips the prompt on every path
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        prefix, sep, suffix = match.group(1).strip().partition(":")
        key = f"{prefix.lower()}{sep}{suffix}"
        if key in sections:
            raise ValueError(f"task.md has duplicate section '## {key}': {path}")
        stop = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        sections[key] = body[match.end():stop].strip()
    instruction = sections.get("prompt", body[: matches[0].start()].strip())
    return _ESCAPED_SECTION_RE.sub(r"\1", instruction)


def _reject_authoring_shorthands(data: dict[str, Any], path: Path) -> None:
    """Refuse five BenchFlow frontmatter shorthands by name.

    BenchFlow expands ``verifier: <path>``, ``oracle: <path>``, ``image:`` and
    ``profile:``/``profiles:`` into the canonical tables (a grader directory,
    an image, presets for network, workdir and timeouts); reading past them
    would grade the task under other rules than BenchFlow's. Only these five
    are refused. Other keys BenchFlow acts on (``agent.prompt_prefix``,
    multi-role ``agents``/``scenes``/``user``, ``verifier.type``,
    ``solution:``, ``sandbox.image``, ...) are still read past without an
    error; checking the whole frontmatter against BenchFlow's ``TaskConfig``
    is a follow-up.
    """

    for key in ("verifier", "oracle"):
        if data.get(key) is not None and not isinstance(data[key], dict):
            raise ValueError(
                f"task.md '{key}: <path>' shorthand is not supported; use a "
                f"'{key}' table and the conventional '{key}/' directory: {path}"
            )
    for key in ("image", "profile", "profiles"):
        if key in data:
            raise ValueError(
                f"task.md '{key}:' shorthand is not supported; write the "
                f"canonical sandbox/agent/verifier tables instead: {path}"
            )


def _plain(value: Any) -> Any:
    """Make a parsed config JSON-serialisable, whichever layout it came from.

    YAML turns an unquoted ``2024-01-02`` into a ``date`` (also as a mapping
    key) and ``!!set`` into a ``set``; TOML has date, time and datetime
    values. The run artifact's ``json.dumps`` rejects all of them, after every
    cell has already run. Dates and times become ISO 8601 strings (a datetime
    as ``2024-01-02T10:30:00``), keys are converted the same way, and sets
    become sorted lists.
    """
    if isinstance(value, dict):
        return {_plain(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_plain(v) for v in value), key=str)
    if isinstance(value, (datetime.date, datetime.time)):  # datetime is a date
        return value.isoformat()
    return value


def _first_dir(root: Path, names: tuple[str, ...]) -> Path:
    for name in names:
        if (root / name).is_dir():
            return root / name
    # Neither exists: name the format's primary directory so the caller's
    # error message points at what the task should have shipped.
    return root / names[0]


def _table(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


# Docker-harness defaults for a task that does not set its own.
_DEFAULT_BUILD_TIMEOUT = 600.0
_DEFAULT_VERIFY_TIMEOUT = 180.0


def _is_public(task: TaskSpec) -> bool:
    return str(task.environment.get("network_mode") or "none") == "public"


def _task_build_timeout(task: TaskSpec) -> float:
    """Image build timeout: the task's ``environment.build_timeout_sec`` if set,
    else :data:`_DEFAULT_BUILD_TIMEOUT`."""
    val = task.environment.get("build_timeout_sec")
    try:
        return float(val) if val is not None else _DEFAULT_BUILD_TIMEOUT
    except (TypeError, ValueError):
        return _DEFAULT_BUILD_TIMEOUT


def _task_verify_timeout(task: TaskSpec) -> float:
    """Verifier timeout: the task's ``verifier.timeout_sec`` if set, else
    :data:`_DEFAULT_VERIFY_TIMEOUT`."""
    val = task.verifier.get("timeout_sec")
    try:
        return float(val) if val is not None else _DEFAULT_VERIFY_TIMEOUT
    except (TypeError, ValueError):
        return _DEFAULT_VERIFY_TIMEOUT
