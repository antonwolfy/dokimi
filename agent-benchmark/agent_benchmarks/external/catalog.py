"""Read external skill/task catalogs (e.g. uxlfoundation/skills) for reuse.

An "external catalog" is any local checkout of a repo that ships skills
(``SKILL.md`` packages) and/or executable tasks (Harbor task directories)
this repo did not author. Callers are expected to have already cloned the
repo themselves -- nothing here fetches anything over the network.

Two manifest conventions are understood, both from uxlfoundation/skills:

- ``<root>/skills.yaml`` -- a flat list of skill entries with a
  ``catalog_path`` relative to *root*.
- ``<root>/evaluation/harbor/suites.json`` -- suites of task entries, some
  of which are declared but not yet implemented (``status: "planned"``) or
  are not executable Harbor tasks at all (``track: "answer-quality"``).

When a root has no such manifest, both readers fall back to a bare
filesystem scan via the existing skill/task loaders.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from agent_benchmarks.harnesses.tasks import TaskSpec, discover_tasks, load_task
from agent_benchmarks.skills import Skill, discover_skills, load_skill

DEFAULT_TASKS_SUBDIR = "evaluation/harbor/tasks"
DEFAULT_SUITES_MANIFEST = "evaluation/harbor/suites.json"


def _within(path: Path, root: Path) -> bool:
    """Whether *path* resolves to somewhere inside *root*.

    Manifest-declared paths (``catalog_path``, task ``name``) come from a
    file the external repo controls, not the caller -- a value like
    ``"../../etc"`` must not let a scan read or report on files outside the
    checkout the caller pointed us at.
    """
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


@dataclass
class SkillCatalogEntry:
    """One skill as reported by a catalog scan."""

    name: str
    status: Optional[str]
    path: Optional[Path]
    source_root: Path
    skill: Optional[Skill] = None
    error: Optional[str] = None

    @property
    def loaded(self) -> bool:
        return self.skill is not None and self.error is None


@dataclass
class TaskCatalogEntry:
    """One task as reported by a catalog scan.

    Three outcomes, not two. ``skipped`` is a declared entry a scan is
    *expected* to pass over -- ``status: "planned"`` with no task directory on
    disk yet, or a ``track`` this repo's ``tasks run`` doesn't drive.
    ``failed`` is an entry that should have worked and didn't. Only ``failed``
    makes ``catalog scan`` exit non-zero, which is the reason a pre-flight scan
    is worth running at all: collapsing both into ``skipped`` reports a catalog
    that cannot run as clean, using the same word the benign cases print.
    """

    name: str
    status: Optional[str]
    track: Optional[str]
    path: Optional[Path]
    task: Optional[TaskSpec] = None
    skipped: bool = False
    failed: bool = False
    reason: Optional[str] = None

    @property
    def loaded(self) -> bool:
        return self.task is not None and not self.skipped and not self.failed


def read_skill_manifest(root: Path) -> list[SkillCatalogEntry]:
    """Read skills under *root*, preferring a ``skills.yaml`` manifest."""

    root = Path(root)
    manifest_path = root / "skills.yaml"
    if not manifest_path.is_file():
        return [
            SkillCatalogEntry(
                name=skill.name,
                status=None,
                path=skill.path.parent,
                source_root=root,
                skill=skill,
            )
            for skill in discover_skills(root)
        ]

    import yaml

    try:
        data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid skills.yaml at {manifest_path}: {exc}") from exc

    entries: list[SkillCatalogEntry] = []
    for item in data.get("skills") or []:
        name = str(item.get("name") or "").strip()
        status = item.get("status")
        catalog_path = item.get("catalog_path")
        path = (root / catalog_path) if catalog_path else None
        skill: Optional[Skill] = None
        error: Optional[str] = None
        if path is None:
            error = "manifest entry is missing catalog_path"
        elif not _within(path, root):
            error = f"catalog_path escapes root: {catalog_path!r}"
        else:
            try:
                skill = load_skill(path)
            except (FileNotFoundError, ValueError) as exc:
                error = str(exc)
        entries.append(
            SkillCatalogEntry(
                name=name or (path.name if path else "?"),
                status=status,
                path=path,
                source_root=root,
                skill=skill,
                error=error,
            )
        )
    return entries


def read_task_manifest(
    root: Path,
    tasks_subdir: str = DEFAULT_TASKS_SUBDIR,
) -> list[TaskCatalogEntry]:
    """Read tasks under *root*, preferring an ``evaluation/harbor/suites.json``
    suite manifest and cross-checking it against what's actually on disk.
    """

    root = Path(root)
    manifest_path = root / DEFAULT_SUITES_MANIFEST
    tasks_root = root / tasks_subdir
    if not manifest_path.is_file():
        return [
            TaskCatalogEntry(
                name=task.name,
                status=None,
                track=None,
                path=task.path,
                task=task,
            )
            for task in discover_tasks(tasks_root)
        ]

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid suites.json at {manifest_path}: {exc}") from exc

    entries: list[TaskCatalogEntry] = []
    for suite in data.get("suites") or []:
        for item in suite.get("tasks") or []:
            name = str(item.get("name") or "").strip()
            status = item.get("status")
            track = item.get("track")
            task_dir = tasks_root / name

            if not _within(task_dir, tasks_root):
                # A failure, not a skip: the manifest asked us to leave the
                # checkout, which is the same thing ``read_skill_manifest``
                # reports as an error for ``catalog_path``.
                entries.append(
                    TaskCatalogEntry(
                        name=name,
                        status=status,
                        track=track,
                        path=None,
                        failed=True,
                        reason=f"task name escapes tasks root: {name!r}",
                    )
                )
                continue

            if not (task_dir / "task.toml").is_file():
                entries.append(
                    TaskCatalogEntry(
                        name=name,
                        status=status,
                        track=track,
                        path=None,
                        skipped=True,
                        reason=f"no task.toml under {task_dir} (manifest status={status!r})",
                    )
                )
                continue

            if track != "executable":
                entries.append(
                    TaskCatalogEntry(
                        name=name,
                        status=status,
                        track=track,
                        path=task_dir,
                        skipped=True,
                        reason=f"track={track!r} is not an executable Harbor task",
                    )
                )
                continue

            try:
                task = load_task(task_dir)
            except (FileNotFoundError, ValueError) as exc:
                # The entry is declared executable and its directory is on
                # disk, so this is the case the scan exists to catch.
                entries.append(
                    TaskCatalogEntry(
                        name=name,
                        status=status,
                        track=track,
                        path=task_dir,
                        failed=True,
                        reason=f"failed to load: {exc}",
                    )
                )
                continue

            entries.append(
                TaskCatalogEntry(
                    name=name,
                    status=status,
                    track=track,
                    path=task_dir,
                    task=task,
                )
            )
    return entries
