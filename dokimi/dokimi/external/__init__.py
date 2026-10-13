# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Scan external skill/task catalogs (e.g. uxlfoundation/skills) for reuse."""

from .catalog import (
    SkillCatalogEntry,
    TaskCatalogEntry,
    read_skill_manifest,
    read_task_manifest,
)

__all__ = [
    "SkillCatalogEntry",
    "TaskCatalogEntry",
    "read_skill_manifest",
    "read_task_manifest",
]
