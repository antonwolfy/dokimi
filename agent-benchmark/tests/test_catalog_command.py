"""CLI coverage for `catalog scan` against external skill/task catalogs."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_benchmarks.cli import build_parser


def _write_skill(root: Path, name: str) -> None:
    skill_dir = root / "skills" / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Use for {name} things.\n---\n# {name}\n",
        encoding="utf-8",
    )


def _write_task(root: Path, name: str) -> None:
    task_dir = root / "evaluation" / "harbor" / "tasks" / name
    (task_dir / "environment").mkdir(parents=True)
    (task_dir / "tests").mkdir()
    (task_dir / "solution").mkdir()
    (task_dir / "instruction.md").write_text("Do the thing.", encoding="utf-8")
    (task_dir / "task.toml").write_text(
        '[metadata]\ndifficulty = "easy"\n\n[agent]\ntimeout_sec = 60\n\n'
        '[verifier]\ntimeout_sec = 10\n\n[environment]\n',
        encoding="utf-8",
    )


def _write_manifests(root: Path) -> None:
    (root / "skills.yaml").write_text(
        'schema_version: "1"\n'
        'skills:\n'
        '  - name: "uxl-onetbb"\n'
        '    status: "incubating"\n'
        '    catalog_path: "skills/uxl-onetbb"\n',
        encoding="utf-8",
    )
    (root / "evaluation" / "harbor").mkdir(parents=True, exist_ok=True)
    (root / "evaluation" / "harbor" / "suites.json").write_text(
        """
        {
          "schema_version": "1.0",
          "suites": [
            {
              "skill": "uxl-onetbb",
              "tasks": [
                {"name": "onetbb-real-task", "status": "implemented", "track": "executable"},
                {"name": "onetbb-planned-task", "status": "planned", "track": "executable"}
              ]
            }
          ]
        }
        """,
        encoding="utf-8",
    )


def test_catalog_scan_reports_skills_and_tasks(tmp_path, capsys):
    _write_skill(tmp_path, "uxl-onetbb")
    _write_task(tmp_path, "onetbb-real-task")
    _write_manifests(tmp_path)

    parser = build_parser()
    args = parser.parse_args(["catalog", "scan", "--root", str(tmp_path)])
    args.func(args)

    out = capsys.readouterr().out
    assert "uxl-onetbb" in out
    assert "onetbb-real-task" in out
    assert "ok" in out
    assert "skipped" in out  # onetbb-planned-task has no task.toml on disk


def test_catalog_scan_kind_filters_to_skills_only(tmp_path, capsys):
    _write_skill(tmp_path, "uxl-onetbb")
    _write_task(tmp_path, "onetbb-real-task")
    _write_manifests(tmp_path)

    parser = build_parser()
    args = parser.parse_args(
        ["catalog", "scan", "--root", str(tmp_path), "--kind", "skills"]
    )
    args.func(args)

    out = capsys.readouterr().out
    assert "uxl-onetbb" in out
    assert "onetbb-real-task" not in out


def test_catalog_scan_exits_nonzero_on_load_error(tmp_path, capsys):
    # Manifest declares a skill whose catalog_path doesn't exist -> real error,
    # not a benign "planned"/non-executable skip.
    (tmp_path / "skills.yaml").write_text(
        'schema_version: "1"\n'
        'skills:\n'
        '  - name: "uxl-ghost"\n'
        '    status: "incubating"\n'
        '    catalog_path: "skills/does-not-exist"\n',
        encoding="utf-8",
    )

    parser = build_parser()
    args = parser.parse_args(
        ["catalog", "scan", "--root", str(tmp_path), "--kind", "skills"]
    )
    with pytest.raises(SystemExit) as exc_info:
        args.func(args)
    assert exc_info.value.code == 1


def test_catalog_scan_rejects_missing_root(tmp_path):
    parser = build_parser()
    args = parser.parse_args(
        ["catalog", "scan", "--root", str(tmp_path / "does-not-exist")]
    )
    with pytest.raises(SystemExit):
        args.func(args)


def test_catalog_scan_reports_clean_error_on_malformed_manifest(tmp_path):
    # A syntax error in the external repo's own manifest must produce a
    # readable CLI error, not a raw traceback.
    (tmp_path / "skills.yaml").write_text("skills: [this is not: valid: yaml:", encoding="utf-8")

    parser = build_parser()
    args = parser.parse_args(
        ["catalog", "scan", "--root", str(tmp_path), "--kind", "skills"]
    )
    with pytest.raises(SystemExit) as exc_info:
        args.func(args)
    assert "invalid skills.yaml" in str(exc_info.value)
