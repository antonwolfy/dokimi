# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Pytest configuration."""

import sys
from pathlib import Path

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# A body token no other fixture or source file contains, so an assertion that the skill text
# reached a prompt cannot pass on some incidental substring.
DEMO_SKILL_MARKER = "demo_marker()"


@pytest.fixture
def demo_skill(tmp_path: Path) -> Path:
    """A minimal on-disk skill directory: ``<tmp>/demo-skill/SKILL.md``.

    The framework loads skills by path, so tests about arm naming, context assembly and
    telemetry need *a* skill, not a particular product's skill. The directory name is what
    :func:`load_skill` derives the arm name from, hence ``skill:demo-skill``.
    """
    d = tmp_path / "demo-skill"
    d.mkdir()
    (d / "SKILL.md").write_text(
        "---\n"
        "name: demo-skill\n"
        "description: A minimal skill used as a test fixture.\n"
        "---\n"
        "# Demo skill\n\n"
        f"Call {DEMO_SKILL_MARKER} before answering.\n",
        encoding="utf-8",
    )
    return d
