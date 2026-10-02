# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Agent skills: load ``SKILL.md`` packages for skill-augmented evaluation."""

from .loader import Skill, load_skill, discover_skills

__all__ = ["Skill", "load_skill", "discover_skills"]
