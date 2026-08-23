"""Tests for scanning external skill/task catalogs (uxlfoundation/skills shape)."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_benchmarks.external import read_skill_manifest, read_task_manifest


def _write_skill(root: Path, name: str) -> None:
    skill_dir = root / "skills" / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Use for {name} things.\n---\n# {name}\n",
        encoding="utf-8",
    )


def _write_task(root: Path, tasks_subdir: str, name: str) -> None:
    task_dir = root / tasks_subdir / name
    (task_dir / "environment").mkdir(parents=True)
    (task_dir / "tests").mkdir()
    (task_dir / "solution").mkdir()
    (task_dir / "instruction.md").write_text("Do the thing.", encoding="utf-8")
    (task_dir / "task.toml").write_text(
        '[metadata]\ndifficulty = "easy"\n\n[agent]\ntimeout_sec = 60\n\n'
        '[verifier]\ntimeout_sec = 10\n\n[environment]\n',
        encoding="utf-8",
    )


# ── skills.yaml manifest ──────────────────────────────────────────────────────


def test_read_skill_manifest_loads_declared_entry(tmp_path):
    _write_skill(tmp_path, "uxl-onetbb")
    (tmp_path / "skills.yaml").write_text(
        'schema_version: "1"\n'
        'skills:\n'
        '  - name: "uxl-onetbb"\n'
        '    status: "incubating"\n'
        '    catalog_path: "skills/uxl-onetbb"\n',
        encoding="utf-8",
    )

    entries = read_skill_manifest(tmp_path)
    assert len(entries) == 1
    assert entries[0].loaded
    assert entries[0].name == "uxl-onetbb"
    assert entries[0].status == "incubating"


def test_read_skill_manifest_reports_missing_path_without_raising(tmp_path):
    (tmp_path / "skills.yaml").write_text(
        'schema_version: "1"\n'
        'skills:\n'
        '  - name: "uxl-ghost"\n'
        '    status: "incubating"\n'
        '    catalog_path: "skills/does-not-exist"\n',
        encoding="utf-8",
    )

    entries = read_skill_manifest(tmp_path)
    assert len(entries) == 1
    assert not entries[0].loaded
    assert entries[0].error


def test_read_skill_manifest_falls_back_to_bare_scan_without_manifest(tmp_path):
    _write_skill(tmp_path, "bare-skill")

    entries = read_skill_manifest(tmp_path)
    assert [e.name for e in entries] == ["bare-skill"]
    assert entries[0].loaded
    assert entries[0].status is None


# ── suites.json manifest ──────────────────────────────────────────────────────


def test_read_task_manifest_loads_executable_and_skips_the_rest(tmp_path):
    _write_task(tmp_path, "evaluation/harbor/tasks", "onetbb-real-task")
    _write_task(tmp_path, "evaluation/harbor/tasks", "onetbb-real-task-answer-quality")
    (tmp_path / "evaluation" / "harbor").mkdir(parents=True, exist_ok=True)
    (tmp_path / "evaluation" / "harbor" / "suites.json").write_text(
        """
        {
          "schema_version": "1.0",
          "suites": [
            {
              "skill": "uxl-onetbb",
              "tasks": [
                {"name": "onetbb-real-task", "status": "implemented", "track": "executable"},
                {"name": "onetbb-planned-task", "status": "planned", "track": "executable"},
                {"name": "onetbb-real-task-answer-quality", "status": "implemented", "track": "answer-quality"}
              ]
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    entries = read_task_manifest(tmp_path)
    by_name = {e.name: e for e in entries}
    assert len(entries) == 3

    assert by_name["onetbb-real-task"].loaded
    assert not by_name["onetbb-real-task"].skipped

    assert by_name["onetbb-planned-task"].skipped
    assert not by_name["onetbb-planned-task"].loaded
    assert "no task.toml" in by_name["onetbb-planned-task"].reason

    assert by_name["onetbb-real-task-answer-quality"].skipped
    assert "not an executable Harbor task" in by_name["onetbb-real-task-answer-quality"].reason

    # Both of these are the *expected* kind of not-loaded, so neither may reach
    # the scan's exit code -- the other half of separating skips from failures.
    assert not by_name["onetbb-planned-task"].failed
    assert not by_name["onetbb-real-task-answer-quality"].failed


def test_read_task_manifest_falls_back_to_bare_scan_without_manifest(tmp_path):
    _write_task(tmp_path, "evaluation/harbor/tasks", "bare-task")

    entries = read_task_manifest(tmp_path)
    assert [e.name for e in entries] == ["bare-task"]
    assert entries[0].loaded
    assert entries[0].status is None


# ── malicious/malformed manifests ──────────────────────────────────────────────


def test_read_skill_manifest_rejects_catalog_path_escaping_root(tmp_path):
    # A malicious skills.yaml could otherwise make the scanner read (and
    # report on) an arbitrary file outside the checkout the caller pointed
    # us at.
    secret = tmp_path.parent / "secret-outside-root"
    secret.mkdir(exist_ok=True)
    (secret / "SKILL.md").write_text(
        "---\nname: escaped\ndescription: should never load.\n---\n", encoding="utf-8"
    )
    (tmp_path / "skills.yaml").write_text(
        'schema_version: "1"\n'
        'skills:\n'
        f'  - name: "evil"\n'
        f'    catalog_path: "../{secret.name}"\n',
        encoding="utf-8",
    )

    entries = read_skill_manifest(tmp_path)
    assert len(entries) == 1
    assert not entries[0].loaded
    assert "escapes root" in entries[0].error


def test_read_task_manifest_rejects_task_name_escaping_tasks_root(tmp_path):
    (tmp_path / "evaluation" / "harbor").mkdir(parents=True)
    (tmp_path / "evaluation" / "harbor" / "suites.json").write_text(
        """
        {
          "suites": [
            {"skill": "x", "tasks": [
              {"name": "../../escaped-task", "status": "implemented", "track": "executable"}
            ]}
          ]
        }
        """,
        encoding="utf-8",
    )

    entries = read_task_manifest(tmp_path)
    assert len(entries) == 1
    assert not entries[0].loaded
    assert "escapes tasks root" in entries[0].reason
    # Classified as a failure, not a skip: a rejected traversal must reach the
    # scan's exit code, the way the skills side already reports `catalog_path
    # escapes root` as an error. Reported as a skip it would print the same
    # word as a benign `status: "planned"` entry and exit 0.
    assert entries[0].failed
    assert not entries[0].skipped


def test_read_task_manifest_reports_a_broken_present_task_as_a_failure(tmp_path):
    # Declared executable, directory on disk, unparseable task.toml. Reported
    # as a skip this reads exactly like `status: "planned"` and the scan exits
    # 0 -- so a pre-flight scan of a catalog that cannot run says it is clean.
    _write_task(tmp_path, "evaluation/harbor/tasks", "onetbb-broken-task")
    (tmp_path / "evaluation/harbor/tasks/onetbb-broken-task/task.toml").write_text(
        "[metadata\ndifficulty = \"easy\"\n", encoding="utf-8"
    )
    (tmp_path / "evaluation" / "harbor" / "suites.json").write_text(
        '{"suites": [{"skill": "x", "tasks": ['
        '{"name": "onetbb-broken-task", "status": "implemented", "track": "executable"}'
        ']}]}',
        encoding="utf-8",
    )

    entries = read_task_manifest(tmp_path)
    assert len(entries) == 1
    assert not entries[0].loaded
    assert entries[0].failed
    assert not entries[0].skipped
    assert "failed to load" in entries[0].reason


def test_read_task_manifest_reports_a_task_missing_instruction_as_a_failure(tmp_path):
    # The other way `load_task` refuses an on-disk task: a valid task.toml with
    # a required file missing. Same classification as the malformed-TOML case.
    _write_task(tmp_path, "evaluation/harbor/tasks", "onetbb-no-instruction")
    (tmp_path / "evaluation/harbor/tasks/onetbb-no-instruction/instruction.md").unlink()
    (tmp_path / "evaluation" / "harbor" / "suites.json").write_text(
        '{"suites": [{"skill": "x", "tasks": ['
        '{"name": "onetbb-no-instruction", "status": "implemented", "track": "executable"}'
        ']}]}',
        encoding="utf-8",
    )

    entries = read_task_manifest(tmp_path)
    assert len(entries) == 1
    assert entries[0].failed
    assert not entries[0].skipped


def test_read_skill_manifest_raises_clear_error_on_malformed_yaml(tmp_path):
    (tmp_path / "skills.yaml").write_text("skills: [this is not: valid: yaml:", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid skills.yaml"):
        read_skill_manifest(tmp_path)


def test_read_task_manifest_raises_clear_error_on_malformed_json(tmp_path):
    (tmp_path / "evaluation" / "harbor").mkdir(parents=True)
    (tmp_path / "evaluation" / "harbor" / "suites.json").write_text(
        "{not valid json", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="invalid suites.json"):
        read_task_manifest(tmp_path)
