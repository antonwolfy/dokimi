# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for the two executable-task layouts (Harbor and BenchFlow ``task.md``).

The ``task.md`` fixture mirrors a real SkillsBench task
(benchflow-ai/skillsbench ``tasks/parallel-tfidf-search``, schema 1.3): YAML
frontmatter with a ``sandbox`` table, ``oracle/``, ``verifier/`` and
task-bundled ``environment/skills``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_benchmarks.coverage import _task_product_tags
from agent_benchmarks.external.catalog import read_task_manifest
from agent_benchmarks.harnesses import discover_tasks, load_task
from agent_benchmarks.harnesses.command import _parse_reward_text
from agent_benchmarks.harnesses.tasks import (
    FORMAT_HARBOR,
    FORMAT_TASK_MD,
    read_task_config,
    task_format,
)

_TASK_MD = """---
schema_version: '1.3'
metadata:
  author_name: Someone
  difficulty: medium
  category: software-engineering
  tags:
  - parallel
  - onetbb
verifier:
  type: test-script
  timeout_sec: 900.0
  env:
    LITERAL: "1"
    SECRET: ${HOST_SECRET}
agent:
  timeout_sec: 1800.0
sandbox:
  network_mode: public
  cpus: 8
  memory_mb: 4096
  gpus: 0
oracle:
  env:
    MODE: oracle
---

# Parallel TF-IDF Similarity Search

In `/root/workspace/`, parallelize the engine.
"""


def _task_md(root: Path, name: str = "sb-task", text: str = _TASK_MD) -> Path:
    task = root / name
    for sub in ("environment/skills/python-parallelization", "oracle", "verifier"):
        (task / sub).mkdir(parents=True, exist_ok=True)
    (task / "environment" / "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")
    (task / "environment" / "skills" / "python-parallelization" / "SKILL.md").write_text(
        "---\nname: python-parallelization\ndescription: d\n---\nbody\n", encoding="utf-8"
    )
    (task / "oracle" / "solve.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    (task / "verifier" / "test.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    (task / "task.md").write_text(text, encoding="utf-8")
    return task


def _harbor(root: Path, name: str = "hb-task") -> Path:
    task = root / name
    for sub in ("environment", "solution", "tests"):
        (task / sub).mkdir(parents=True)
    (task / "instruction.md").write_text("Fix it.", encoding="utf-8")
    (task / "task.toml").write_text(
        '[metadata]\ntags = ["onedal"]\n\n[environment]\nworkdir = "/app"\n', encoding="utf-8"
    )
    return task


# ── loader ────────────────────────────────────────────────────────────────────


def test_task_md_loads_frontmatter_and_body(tmp_path):
    task = load_task(_task_md(tmp_path))
    assert task.format == FORMAT_TASK_MD
    assert task.schema_version == "1.3"
    assert task.metadata["tags"] == ["parallel", "onetbb"]
    assert task.timeout_sec == 1800.0
    assert task.verifier["timeout_sec"] == 900.0
    assert task.instruction.startswith("# Parallel TF-IDF")
    assert task.instruction.endswith("parallelize the engine.")  # stripped, as BenchFlow
    assert "---" not in task.instruction


_MINIMAL_FRONTMATTER = "---\nschema_version: '1.3'\nsandbox:\n  network_mode: public\n---\n"


def test_task_md_prompt_section_is_the_instruction(tmp_path):
    """Only ``## prompt`` reaches the agent; role/scene/persona text stays out (BenchFlow)."""
    body = (
        "## prompt\n\nreal prompt\n\n## role:reviewer\n\nsecret reviewer text\n\n"
        "## scene:review\n\nscene text\n\n## user-persona\n\npersona text\n"
    )
    task = load_task(_task_md(tmp_path, text=_MINIMAL_FRONTMATTER + body))
    assert task.instruction == "real prompt"


@pytest.mark.parametrize("heading", ["## user-persona", "## scene:review", "## role:x"])
def test_task_md_any_reserved_heading_ends_the_prompt(tmp_path, heading):
    body = f"## prompt\n\nreal prompt\n\n{heading}\n\nnot for the agent\n"
    task = load_task(_task_md(tmp_path, text=_MINIMAL_FRONTMATTER + body))
    assert task.instruction == "real prompt"


def test_task_md_without_prompt_heading_uses_the_preamble(tmp_path):
    body = "Do the thing.\n\n## role:reviewer\n\nsecret reviewer text\n"
    task = load_task(_task_md(tmp_path, text=_MINIMAL_FRONTMATTER + body))
    assert task.instruction == "Do the thing."


def test_task_md_escaped_section_heading_is_restored_in_the_prompt(tmp_path):
    body = "## prompt\n\nKeep this line:\n\\## role:x\n"
    task = load_task(_task_md(tmp_path, text=_MINIMAL_FRONTMATTER + body))
    assert task.instruction == "Keep this line:\n## role:x"


def test_task_md_duplicate_section_is_rejected(tmp_path):
    body = "## prompt\n\na\n\n## PROMPT\n\nb\n"
    with pytest.raises(ValueError, match="duplicate section"):
        load_task(_task_md(tmp_path, text=_MINIMAL_FRONTMATTER + body))


def test_task_md_verifier_path_shorthand_is_rejected(tmp_path):
    path = _task_md(tmp_path, text="---\nverifier: checks\n---\nDo it.\n")
    (path / "checks").mkdir()
    (path / "checks" / "test.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    with pytest.raises(ValueError, match="verifier"):
        load_task(path)


def test_task_md_oracle_path_shorthand_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="oracle"):
        load_task(_task_md(tmp_path, text="---\noracle: gold\n---\nDo it.\n"))


@pytest.mark.parametrize(
    "line, key",
    [
        ("profile: code-change", "profile"),
        ("profiles: [code-change]", "profiles"),
        ("image: python:3.12", "image"),
    ],
)
def test_task_md_profile_and_image_shorthand_are_rejected(tmp_path, line, key):
    with pytest.raises(ValueError, match=f"'{key}:'"):
        load_task(_task_md(tmp_path, text=f"---\n{line}\n---\nDo it.\n"))


def test_task_md_sandbox_table_feeds_environment(tmp_path):
    """Schema 1.3 renamed [environment] to [sandbox]; consumers read .environment."""
    task = load_task(_task_md(tmp_path))
    assert task.environment["network_mode"] == "public"
    assert task.environment["cpus"] == 8


def test_as_dict_carries_every_table(tmp_path):
    """The run record's tasks block keeps oracle settings, e.g. oracle.env."""
    record = load_task(_task_md(tmp_path)).as_dict()
    assert record["oracle"] == {"env": {"MODE": "oracle"}}
    assert record["format"] == FORMAT_TASK_MD
    assert record["environment"]["cpus"] == 8


def test_task_md_layout_dirs(tmp_path):
    task = load_task(_task_md(tmp_path))
    assert task.solution_dir.name == "oracle"
    assert task.tests_dir.name == "verifier"
    assert task.skills_dir is not None and task.skills_dir.name == "skills"


def test_harbor_layout_dirs_and_no_skills(tmp_path):
    task = load_task(_harbor(tmp_path))
    assert task.format == FORMAT_HARBOR
    assert task.solution_dir.name == "solution"
    assert task.tests_dir.name == "tests"
    assert task.skills_dir is None


def test_layout_dirs_fall_back_to_the_other_convention(tmp_path):
    """BenchFlow accepts tests/ and solution/ as aliases inside a task.md task."""
    path = _task_md(tmp_path)
    (path / "oracle").rename(path / "solution")
    (path / "verifier").rename(path / "tests")
    task = load_task(path)
    assert task.solution_dir.name == "solution"
    assert task.tests_dir.name == "tests"


def test_directory_with_both_files_loads_as_task_md(tmp_path):
    """`bench tasks migrate` without --remove-legacy leaves both behind."""
    path = _task_md(tmp_path)
    (path / "task.toml").write_text("[metadata]\ntags = ['stale']\n", encoding="utf-8")
    (path / "instruction.md").write_text("stale", encoding="utf-8")
    assert task_format(path) == FORMAT_TASK_MD
    assert load_task(path).metadata["tags"] == ["parallel", "onetbb"]


@pytest.mark.parametrize(
    "text, match",
    [
        ("# no frontmatter\n", "no YAML frontmatter"),
        ("---\nmetadata: {}\n", "not closed"),
        ("---\n- a\n- b\n---\nbody\n", "must be a mapping"),
        ("---\nmetadata: [unclosed\n---\nbody\n", "not valid YAML"),
    ],
)
def test_malformed_task_md_is_a_value_error(tmp_path, text, match):
    with pytest.raises(ValueError, match=match):
        load_task(_task_md(tmp_path, text=text))


def test_discover_mixes_both_layouts(tmp_path):
    _task_md(tmp_path, "a-sb")
    _harbor(tmp_path, "b-hb")
    (tmp_path / "c-not-a-task").mkdir()
    tasks = discover_tasks(tmp_path)
    assert [(t.name, t.format) for t in tasks] == [
        ("a-sb", FORMAT_TASK_MD), ("b-hb", FORMAT_HARBOR),
    ]


def test_read_task_config_needs_no_instruction(tmp_path):
    path = _harbor(tmp_path)
    (path / "instruction.md").unlink()
    assert read_task_config(path)["metadata"]["tags"] == ["onedal"]


def test_read_task_config_bad_toml_is_a_value_error(tmp_path):
    path = _harbor(tmp_path)
    (path / "task.toml").write_text("[metadata\n", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid TOML"):
        read_task_config(path)


def test_coverage_reads_tags_from_both_layouts(tmp_path):
    _task_md(tmp_path, "a-sb")
    _harbor(tmp_path, "b-hb")
    tags = _task_product_tags(tmp_path)
    assert tags == {"a-sb": {"parallel", "onetbb"}, "b-hb": {"onedal"}}


def test_catalog_scan_accepts_task_md(tmp_path):
    _task_md(tmp_path / "evaluation" / "harbor" / "tasks", "a-sb")
    entries = read_task_manifest(tmp_path)
    assert [(e.name, e.failed, e.skipped) for e in entries] == [("a-sb", False, False)]


def test_catalog_suites_manifest_entry_can_be_a_task_md_task(tmp_path):
    import json

    _task_md(tmp_path / "evaluation" / "harbor" / "tasks", "a-sb")
    (tmp_path / "evaluation" / "harbor" / "suites.json").write_text(
        json.dumps({"suites": [{"tasks": [{"name": "a-sb", "track": "executable"}]}]}),
        encoding="utf-8",
    )
    (entry,) = read_task_manifest(tmp_path)
    assert (entry.failed, entry.skipped) == (False, False)
    assert entry.task is not None and entry.task.format == FORMAT_TASK_MD


def test_coverage_skips_a_task_that_does_not_parse(tmp_path):
    _task_md(tmp_path, "a-bad", text="---\nmetadata: [unclosed\n---\nbody\n")
    _harbor(tmp_path, "b-hb")
    assert _task_product_tags(tmp_path) == {"b-hb": {"onedal"}}


# ── reward parsing ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text, expected",
    [("1", 1.0), ("0\n", 0.0), ("0.75", 0.75), ("1.0", 1.0), ("reward: 0.5", 0.5),
     ("1.5", None), ("-0.1", None), ("", None), ("nan", None), ("inf", None)],
)
def test_reward_file_accepts_partial_credit(text, expected):
    assert _parse_reward_text(text, reward_file=True) == expected


@pytest.mark.parametrize("text, expected", [("0.5", None), ("1e-3", None), ("1", 1.0), ("reward: 0.5", 0.5)])
def test_command_output_keeps_the_old_reward_rule(text, expected):
    """A command printing a bare 0.5 still falls back to its exit code."""
    assert _parse_reward_text(text) == expected


def test_find_reward_keeps_a_fractional_reward_file(tmp_path):
    from agent_benchmarks.harnesses.command import _find_reward

    (tmp_path / "verifier").mkdir()
    (tmp_path / "verifier" / "reward.txt").write_text("0.75\n", encoding="utf-8")
    assert _find_reward(tmp_path, "", "") == 0.75


def test_command_harness_fractional_reward_is_kept_and_fails(tmp_path):
    """Exit 0 used to make this a pass (exit-code fallback); 0.75 is now the reward."""
    from agent_benchmarks.harnesses.command import CommandHarness

    task = load_task(_harbor(tmp_path / "tasks"))
    harness = CommandHarness(
        "fake",
        "sh -c 'mkdir -p {output_dir}/verifier && echo 0.75 > {output_dir}/verifier/reward.txt'",
    )
    result = harness.run(task, output_dir=tmp_path / "out")
    assert result.returncode == 0
    assert (result.reward, result.passed) == (0.75, False)


@pytest.mark.parametrize("text, reward", [("0.75\n", 0.75), ("1.00\n", 1.0)])
def test_docker_verify_keeps_a_fractional_reward_file(tmp_path, monkeypatch, text, reward):
    import agent_benchmarks.harnesses.docker_solver as mod
    from agent_benchmarks.harnesses.docker_solver import DockerSolverHarness

    class _P:
        returncode, stdout = 0, ""

    def _docker(args, log, **kwargs):
        if args[0] == "cp" and args[1].endswith("/logs/verifier/reward.txt"):
            Path(args[2]).write_text(text, encoding="utf-8")
        return _P()

    monkeypatch.setattr(mod, "_docker", _docker)
    out = tmp_path / "o"
    out.mkdir()
    task = load_task(_harbor(tmp_path))
    harness = DockerSolverHarness(harness_id="docker-oracle", mode="oracle")
    assert harness._verify(task, "c1", out, log=None) == reward


def test_yaml_dates_stay_json_serialisable(tmp_path):
    import json

    text = _TASK_MD.replace("  author_name: Someone\n", "  author_name: Someone\n  created: 2024-01-02\n")
    record = load_task(_task_md(tmp_path, text=text)).as_dict()
    assert record["metadata"]["created"] == "2024-01-02"
    json.dumps(record)


def test_yaml_date_keys_sets_and_toml_dates_survive_the_run_artifact(tmp_path, monkeypatch):
    """Converted when the task is loaded, not after every cell has run."""
    from agent_benchmarks.artifacts import save_artifact
    from agent_benchmarks.harnesses import TaskSuiteRunner

    root = tmp_path / "tasks"
    text = _TASK_MD.replace(
        "  author_name: Someone\n",
        "  author_name: Someone\n  history: {2024-01-02: created}\n  labels: !!set {e, b, d, a, c}\n",
    )
    _task_md(root, "a-sb", text=text)
    hb = _harbor(root, "b-hb")
    (hb / "task.toml").write_text(
        '[metadata]\ncreated = 2024-01-02\nupdated = 2024-01-02T10:30:00\nat = 07:32:00\n',
        encoding="utf-8",
    )
    sb, harbor = discover_tasks(root)
    assert sb.metadata["history"] == {"2024-01-02": "created"}
    assert sb.metadata["labels"] == ["a", "b", "c", "d", "e"]
    assert harbor.metadata == {
        "created": "2024-01-02", "updated": "2024-01-02T10:30:00", "at": "07:32:00",
    }
    assert read_task_config(hb)["metadata"]["created"] == "2024-01-02"
    out = TaskSuiteRunner([sb, harbor], ["docker-oracle"], output_root=tmp_path / "runs",
                          dry_run=True).run()
    save_artifact("task_runs", out, tmp_path / "task_runs.json")
    assert (tmp_path / "task_runs.json").is_file()


def test_note_task_md_without_frontmatter_does_not_shadow_task_toml(tmp_path):
    path = _harbor(tmp_path)
    (path / "task.md").write_text("# Notes for task authors\n", encoding="utf-8")
    assert task_format(path) == FORMAT_HARBOR
    assert [t.format for t in discover_tasks(tmp_path)] == [FORMAT_HARBOR]


@pytest.mark.parametrize(
    "text",
    [
        "---\ntitle: Notes on this task\nlayout: page\n---\nAuthor notes: the solution uses X.\n",
        "---\nmetadata: {}\n",  # unclosed block
        "---\n\nA horizontal rule, then notes.\n\n---\nmore\n",  # not a mapping
    ],
    ids=["jekyll", "unclosed", "horizontal-rule"],
)
def test_non_benchflow_task_md_next_to_task_toml_loads_task_toml(tmp_path, text):
    """A docs page next to a Harbor task must not turn it into a task-md task."""
    path = _harbor(tmp_path)
    (path / "task.md").write_text(text, encoding="utf-8")
    with pytest.warns(UserWarning, match="loading task.toml") as caught:
        assert task_format(path) == FORMAT_HARBOR
        (task,) = discover_tasks(tmp_path)
        assert read_task_config(path)["metadata"]["tags"] == ["onedal"]
    assert len(caught) == 1  # once, though task_format ran three times
    assert task.format == FORMAT_HARBOR
    assert task.instruction == "Fix it."
    assert task.metadata["tags"] == ["onedal"]
    assert task.environment == {"workdir": "/app"}


def test_benchflow_task_md_next_to_task_toml_wins(tmp_path):
    path = _harbor(tmp_path)
    (path / "task.md").write_text("---\nmetadata:\n  tags: [sb]\n---\nDo it.\n", encoding="utf-8")
    task = load_task(path)
    assert task.format == FORMAT_TASK_MD
    assert task.metadata["tags"] == ["sb"]


def test_stray_task_md_notes_do_not_break_discovery_of_the_root(tmp_path):
    """BenchFlow's batch discovery skips a malformed task; so do we, loudly."""
    root = tmp_path / "evaluation" / "harbor" / "tasks"
    _harbor(root, "good-harbor")
    _task_md(root, "good-sb")
    notes = root / "docs-notes"
    notes.mkdir()
    (notes / "task.md").write_text("# planning notes\n", encoding="utf-8")
    with pytest.warns(UserWarning, match="docs-notes: task.md has no YAML frontmatter"):
        assert [t.name for t in discover_tasks(root)] == ["good-harbor", "good-sb"]
        entries = read_task_manifest(tmp_path)
    assert [e.name for e in entries] == ["good-harbor", "good-sb"]
    assert set(_task_product_tags(root)) == {"good-harbor", "good-sb"}


def test_lone_task_md_without_frontmatter_is_still_an_error(tmp_path):
    with pytest.raises(ValueError, match="no YAML frontmatter"):
        load_task(_task_md(tmp_path, text="# notes\n"))


def test_environment_and_sandbox_together_is_rejected(tmp_path):
    text = _TASK_MD.replace("sandbox:\n", "environment:\n  cpus: 2\nsandbox:\n")
    with pytest.raises(ValueError, match="both 'environment' and 'sandbox'"):
        load_task(_task_md(tmp_path, text=text))


@pytest.mark.parametrize("harness_id", ["docker-oracle", "docker-claude"])
def test_docker_harness_errors_on_a_task_md_task(tmp_path, monkeypatch, harness_id):
    """Until docker-* mount /oracle and /verifier (#76), a task.md cell is an
    error (missing data), not a verified 0 from a verifier that found no tests."""
    import agent_benchmarks.harnesses.docker_solver as mod
    from agent_benchmarks.harnesses import TaskSuiteRunner

    calls: list[list[str]] = []
    monkeypatch.setattr(mod, "_docker", lambda args, log, **k: calls.append(list(args)))
    task = load_task(_task_md(tmp_path / "tasks"))
    out = TaskSuiteRunner([task], [harness_id], output_root=tmp_path / "runs").run()
    (row,) = out["results"]
    assert row["reward"] is None and row["passed"] is False
    assert "do not run tasks with oracle/ or verifier/" in row["metrics"]["error"]
    assert calls == []


@pytest.mark.parametrize("harness_id", ["terminal-bench:oracle", "codex", "claude-code"])
def test_harbor_harness_errors_on_a_task_md_task(tmp_path, monkeypatch, harness_id):
    """Harbor reads only task.toml: its non-zero exit must not read as a fail."""
    import subprocess

    from agent_benchmarks.harnesses import TaskSuiteRunner

    def _no_subprocess(*args, **kwargs):
        raise AssertionError("harbor must not be started for a task.md task")

    monkeypatch.setattr(subprocess, "run", _no_subprocess)
    task = load_task(_task_md(tmp_path / "tasks"))
    out = TaskSuiteRunner([task], [harness_id], output_root=tmp_path / "runs").run()
    (row,) = out["results"]
    assert row["reward"] is None and row["passed"] is False
    assert "without task.toml" in row["metrics"]["error"]



_MIGRATED = "---\nschema_version: '1.3'\nmetadata:\n  tags: [x]\n---\n\n## prompt\nFix it.\n"


def _recording_docker(monkeypatch):
    import agent_benchmarks.harnesses.docker_solver as mod

    class _P:
        returncode, stdout = 0, ""

    calls: list[list[str]] = []

    def _docker(args, log, **kwargs):
        calls.append(list(args))
        if args[0] == "cp" and args[1].endswith("/logs/verifier/reward.txt"):
            Path(args[2]).write_text("1", encoding="utf-8")
        return _P()

    monkeypatch.setattr(mod, "_docker", _docker)
    return calls


def test_migrated_dir_with_task_toml_and_task_md_runs_everywhere(tmp_path, monkeypatch):
    """`bench tasks migrate` without --remove-legacy leaves task.toml, solution/,
    tests/ and a task.md. Every built-in harness read those files before task.md
    was understood, so none may refuse the directory."""
    import subprocess

    from agent_benchmarks.harnesses import TaskSuiteRunner

    path = _harbor(tmp_path / "tasks")
    (path / "task.md").write_text(_MIGRATED, encoding="utf-8")
    task = load_task(path)
    assert task.format == FORMAT_TASK_MD and task.tests_dir.name == "tests"
    calls = _recording_docker(monkeypatch)
    started: list[list[str]] = []

    class _R:
        returncode, stdout, stderr = 0, "", ""

    monkeypatch.setattr(subprocess, "run", lambda cmd, **k: started.append(cmd) or _R())
    ids = ["docker-oracle", "docker-claude", "terminal-bench:oracle", "codex"]
    out = TaskSuiteRunner([task], ids, output_root=tmp_path / "runs").run()
    # docker-claude starts an egress proxy, which may be missing on the test host;
    # what it must never do is refuse the directory.
    errors = {r["harness"]: (r["metrics"] or {}).get("error", "") for r in out["results"]}
    assert "do not run" not in errors["docker-claude"], errors
    assert not any(v for k, v in errors.items() if k != "docker-claude"), errors
    cps = [(Path(c[1]).name, c[2].split(":", 1)[1]) for c in calls if c[0] == "cp" and Path(c[1]).is_dir()]
    assert ("solution", "/solution") in cps and ("tests", "/tests") in cps
    assert any("harbor" in " ".join(map(str, c)) for c in started)


@pytest.mark.parametrize("harness_id", ["docker-oracle", "docker-claude"])
def test_task_toml_with_only_oracle_and_verifier_dirs_errors_in_docker(
    tmp_path, monkeypatch, harness_id
):
    """They would be copied to /solution and /tests, where the scripts do not
    look: a verified 0 that a no-op solve.sh cannot be told apart from."""
    from agent_benchmarks.harnesses import TaskSuiteRunner

    path = _harbor(tmp_path / "tasks")
    (path / "solution").rename(path / "oracle")
    (path / "tests").rename(path / "verifier")
    calls = _recording_docker(monkeypatch)
    task = load_task(path)
    assert task.format == FORMAT_HARBOR
    out = TaskSuiteRunner([task], [harness_id], output_root=tmp_path / "runs").run()
    (row,) = out["results"]
    assert row["reward"] is None and "oracle/ or verifier/" in row["metrics"]["error"]
    assert calls == []


def test_docker_probe_copies_neither_directory_so_it_is_not_refused(tmp_path):
    from agent_benchmarks.harnesses.docker_solver import DockerSolverHarness

    path = _harbor(tmp_path / "tasks")
    (path / "solution").rename(path / "oracle")
    (path / "tests").rename(path / "verifier")
    result = DockerSolverHarness(harness_id="docker-probe", mode="probe").run(
        load_task(path), dry_run=True
    )
    assert result.metrics["dry_run"] is True


def test_command_harness_still_runs_a_task_md_task(tmp_path):
    from agent_benchmarks.harnesses.command import CommandHarness

    task = load_task(_task_md(tmp_path / "tasks"))
    harness = CommandHarness(
        "fake", "sh -c 'mkdir -p {output_dir}/verifier && echo 1 > {output_dir}/verifier/reward.txt'"
    )
    result = harness.run(task, output_dir=tmp_path / "out")
    assert (result.reward, result.passed) == (1.0, True)


@pytest.mark.parametrize(
    "key, value",
    [
        ("schema_version", "'1.3'"),
        ("metadata", "{tags: [sb]}"),
        ("verifier", "{timeout_sec: 5}"),
        ("agent", "{timeout_sec: 5}"),
        ("sandbox", "{cpus: 1}"),
        ("environment", "{cpus: 1}"),
        ("oracle", "{env: {A: b}}"),
    ],
)
def test_every_benchflow_key_makes_task_md_win_next_to_task_toml(tmp_path, key, value):
    path = _harbor(tmp_path)
    (path / "task.md").write_text(f"---\n{key}: {value}\n---\nDo it.\n", encoding="utf-8")
    assert task_format(path) == FORMAT_TASK_MD
