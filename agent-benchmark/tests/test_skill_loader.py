# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Progressive disclosure over nested skill layouts."""

import pytest

from agent_benchmarks.skills.loader import load_skill
from agent_benchmarks.treatments.tools import ViewSkillTool

SKILL_BODY = """---
name: nested-demo
description: Use when testing nested skill layouts.
---
# nested-demo
"""


@pytest.fixture
def nested_skill(tmp_path):
    """A skill that keeps its detail in subdirectories, as real skills do."""
    root = tmp_path / "nested-demo"
    (root / "references").mkdir(parents=True)
    (root / "scripts").mkdir()
    (root / "SKILL.md").write_text(SKILL_BODY, encoding="utf-8")
    (root / "references" / "topic.md").write_text("# Topic detail", encoding="utf-8")
    (root / "scripts" / "probe.py").write_text("print('probe')\n", encoding="utf-8")
    return root


def test_loader_finds_resources_in_subdirectories(nested_skill):
    skill = load_skill(nested_skill)
    found = {p.relative_to(nested_skill).as_posix() for p in skill.resources}
    assert found == {"references/topic.md", "scripts/probe.py"}


def test_file_picker_offers_nested_markdown_by_relative_path(nested_skill):
    tool = ViewSkillTool(load_skill(nested_skill))
    enum = tool.parameters["properties"]["file"]["enum"]
    assert enum == ["SKILL.md", "references/topic.md"]


def test_nested_file_loads_by_relative_path(nested_skill):
    out = ViewSkillTool(load_skill(nested_skill)).call("references/topic.md")
    assert "Topic detail" in out


def test_manifest_lists_every_bundled_file_relative_to_skill_md(nested_skill):
    manifest = load_skill(nested_skill).resource_manifest()
    assert "references/topic.md" in manifest
    assert "scripts/probe.py" in manifest
    # The judge's problem is existence, so the manifest has to assert it.
    assert "exist" in manifest
    # Paths only — the bodies would not fit the judge's budget.
    assert "Topic detail" not in manifest


def test_manifest_is_empty_for_a_skill_with_no_bundled_files(tmp_path):
    root = tmp_path / "flat-demo"
    root.mkdir()
    (root / "SKILL.md").write_text(SKILL_BODY, encoding="utf-8")
    assert load_skill(root).resource_manifest() == ""


def test_manifest_caps_the_list_and_says_how_many_it_dropped(nested_skill):
    manifest = load_skill(nested_skill).resource_manifest(max_files=1)
    assert "… and 1 more" in manifest


def test_path_traversal_is_refused(nested_skill):
    out = ViewSkillTool(load_skill(nested_skill)).call("../../../../etc/passwd")
    assert "outside the skill directory" in out


def test_single_file_skill_takes_no_parameters(tmp_path):
    root = tmp_path / "flat-demo"
    root.mkdir()
    (root / "SKILL.md").write_text(SKILL_BODY, encoding="utf-8")
    tool = ViewSkillTool(load_skill(root))
    assert tool.parameters == {"type": "object", "properties": {}}
