# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Data models for Phase D evaluation subjects."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


SUBJECT_KINDS = {"skill", "profile", "mcp", "doc-source", "bundle", "repo"}

# Kinds that are not prompt/context treatments, so they have no arm spec and
# cannot be bundle members. A ``repo`` subject is a whole repository (ref is a
# source spec, ``manifest`` its repo-eval.yaml) and is run through ``repo``
# commands (docs/repo-evaluation-contract.md).
NON_ARM_KINDS = {"bundle", "repo"}


@dataclass(frozen=True)
class SubjectMember:
    """One member of a bundle subject."""

    kind: str
    ref: str


@dataclass(frozen=True)
class SubjectArtifact:
    """The artifact under evaluation."""

    id: str
    kind: str
    ref: str | None = None
    members: tuple[SubjectMember, ...] = ()
    manifest: str | None = None


@dataclass(frozen=True)
class SubjectSuite:
    """Question/task suite attached to one subject."""

    products: tuple[str, ...]
    questions: tuple[str, ...]
    tasks: tuple[str, ...] = ()


@dataclass(frozen=True)
class SubjectDescriptor:
    """A loadable Phase D subject descriptor."""

    path: Path
    subject: SubjectArtifact
    suite: SubjectSuite
    baseline: str = "baseline"
    matrix_cells: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    matrix_cells_explicit: bool = False

    @property
    def id(self) -> str:
        return self.subject.id
