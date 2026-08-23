"""Tests for executable coding-task harness support."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from agent_benchmarks.artifacts import validate_artifact
from agent_benchmarks.harnesses import TaskSuiteRunner, load_task
from agent_benchmarks.harnesses.command import CommandHarness
from agent_benchmarks.harnesses.operations import load_operations
from agent_benchmarks.harnesses.registry import create_harness, known_harnesses
from agent_benchmarks.harnesses.runner import summarize_task_results


def _fixture_task(tmp_path: Path) -> Path:
    task = tmp_path / "toy-task"
    (task / "tests").mkdir(parents=True)
    (task / "environment").mkdir()
    (task / "solution").mkdir()
    (task / "instruction.md").write_text("Write solution.py and pass tests.", encoding="utf-8")
    (task / "task.toml").write_text(
        """
[metadata]
difficulty = "easy"
tags = ["toy", "python"]

[agent]
timeout_sec = 12

[verifier]
timeout_sec = 3

[environment]
docker_image = "toy:latest"
allow_internet = false
""",
        encoding="utf-8",
    )
    return task


def test_task_loader_reads_terminal_bench_metadata(tmp_path):
    task = load_task(_fixture_task(tmp_path))
    assert task.name == "toy-task"
    assert task.timeout_sec == 12
    assert task.metadata["tags"] == ["toy", "python"]
    assert "Write solution.py" in task.instruction


def test_known_harness_aliases_render_harbor_commands(tmp_path):
    task = load_task(_fixture_task(tmp_path))
    harness = create_harness("codex")
    cmd = harness.build_command(task, model="gpt-5", output_dir=tmp_path / "out")
    assert cmd[:2] == ["harbor", "run"]
    assert "codex" in cmd
    assert "gpt-5" in cmd
    assert "codex" in known_harnesses()


def test_command_harness_id_includes_template_to_avoid_collisions():
    first = create_harness("command:echo {task}")
    second = create_harness("command:cat {task_path}")
    assert first.harness_id == "command:echo {task}"
    assert second.harness_id == "command:cat {task_path}"


def test_command_template_allows_code_braces_in_template_and_prompt(tmp_path):
    task_path = _fixture_task(tmp_path)
    (task_path / "instruction.md").write_text(
        'Write {"ok": true} into config.py and keep f"{value}" intact.',
        encoding="utf-8",
    )
    task = load_task(task_path)

    literal = CommandHarness("fake", "echo {'literal':1} {task}")
    assert literal.build_command(task, model=None, output_dir=tmp_path / "out") == [
        "echo",
        "{literal:1}",
        "toy-task",
    ]

    prompt = CommandHarness("fake", "echo {prompt_quoted}")
    rendered_prompt = " ".join(prompt.build_command(task, model=None, output_dir=tmp_path / "out"))
    assert '{"ok": true}' in rendered_prompt
    assert 'f"{value}"' in rendered_prompt

    escaped = CommandHarness("fake", "echo {prompt_escaped}")
    rendered_escaped = " ".join(
        escaped.build_command(task, model=None, output_dir=tmp_path / "out")
    )
    assert "{{ok: true}}" in rendered_escaped
    assert "f{{value}}" in rendered_escaped


def test_command_harness_collects_reward_and_operations(tmp_path, monkeypatch):
    task = load_task(_fixture_task(tmp_path))
    out_dir = tmp_path / "out"

    def fake_run(command, cwd, env, text, capture_output, timeout, check):
        Path(env["AGENT_BENCHMARK_OPERATIONS_FILE"]).write_text(
            json.dumps({"type": "tool", "name": "edit", "elapsed_sec": 0.25}) + "\n",
            encoding="utf-8",
        )
        reward_dir = Path(env["AGENT_BENCHMARK_OUTPUT_DIR"]) / "logs" / "verifier"
        reward_dir.mkdir(parents=True)
        (reward_dir / "reward.txt").write_text("1.0", encoding="utf-8")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='AGENT_BENCHMARK_OP {"type":"loop","name":"turn","elapsed_sec":0.1}\n',
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    harness = CommandHarness("fake", "fake-agent --task {task_path} --model {model}")
    result = harness.run(task, model="m", output_dir=out_dir)

    assert result.passed is True
    assert result.reward == 1.0
    assert result.metrics["stdout_bytes"] > 0
    by_type = result.as_dict()["metrics"]["operations_by_type"]
    assert by_type["harness"] == 1
    assert by_type["tool"] == 1
    assert by_type["loop"] == 1


def test_command_harness_uses_finite_timeout_when_task_has_none(tmp_path, monkeypatch):
    task_path = _fixture_task(tmp_path)
    (task_path / "task.toml").write_text('[metadata]\ndifficulty = "easy"\n', encoding="utf-8")
    task = load_task(task_path)
    observed = {}

    def fake_run(command, cwd, env, text, capture_output, timeout, check):
        observed["timeout"] = timeout
        return subprocess.CompletedProcess(command, 0, stdout="reward: 1.0", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = CommandHarness("fake", "fake-agent --task {task_path}").run(
        task, output_dir=tmp_path / "out"
    )

    assert observed["timeout"] == 3600.0
    assert result.metrics["timeout_sec"] == 3600.0


def test_operation_loader_accepts_markers_and_unstructured_lines(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "operations.jsonl").write_text(
        json.dumps({"type": "subagent", "name": "reviewer"}) + "\n",
        encoding="utf-8",
    )
    ops = load_operations(
        out,
        'AGENT_BENCHMARK_OP {"type":"tool","name":"search"}\nloop 1 done',
        "",
    )
    assert [op.type for op in ops] == ["subagent", "tool", "loop"]


def test_operation_loader_defaults_malformed_elapsed(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "operations.jsonl").write_text(
        json.dumps({"type": "tool", "name": "edit", "elapsed_sec": "not-a-number"}) + "\n",
        encoding="utf-8",
    )
    ops = load_operations(out, "", "")
    assert ops[0].elapsed_sec == 0.0


def test_operation_loader_reports_unreadable_jsonl(tmp_path, monkeypatch):
    out = tmp_path / "out"
    out.mkdir()
    log = out / "operations.jsonl"
    log.write_text("{}", encoding="utf-8")

    def fail_read_text(*args, **kwargs):
        raise OSError("boom")

    monkeypatch.setattr(Path, "read_text", fail_read_text)
    ops = load_operations(out, "", "")
    assert ops[0].type == "log_parse_error"
    assert ops[0].status == "error"
    assert "boom" in ops[0].metadata["error"]


def test_task_suite_summary_compares_to_baseline(tmp_path, monkeypatch):
    task = load_task(_fixture_task(tmp_path))

    def fake_run(self, task, *, model=None, output_dir=None, timeout_sec=None, dry_run=False):
        from agent_benchmarks.harnesses.models import HarnessResult, OperationRecord

        passed = self.harness_id == "candidate"
        return HarnessResult(
            harness=self.harness_id,
            task=task.name,
            command=["fake"],
            returncode=0 if passed else 1,
            elapsed_sec=1.0,
            reward=1.0 if passed else 0.0,
            passed=passed,
            operations=[OperationRecord("harness", self.harness_id)],
        )

    monkeypatch.setattr(CommandHarness, "run", fake_run)
    suite = TaskSuiteRunner(
        tasks=[task],
        harnesses=["baseline", "candidate"],
        baseline_harness="baseline",
        command_template="fake {task_path}",
        output_root=tmp_path / "runs",
    )
    output = suite.run()

    validate_artifact("task_runs", output)
    assert output["summary"]["per_harness"]["baseline"]["pass_rate"] == 0.0
    assert output["summary"]["per_harness"]["candidate"]["pass_rate"] == 1.0
    assert output["summary"]["comparisons"]["candidate"]["pass_rate_delta"] == 1.0


def test_summarize_task_results_counts_operations():
    rows = [
        {
            "harness": "h1",
            "passed": True,
            "elapsed_sec": 1,
            "metrics": {"operation_count": 2, "operations_by_type": {"tool": 1, "loop": 1}},
        },
        {
            "harness": "h1",
            "passed": False,
            "elapsed_sec": 2,
            "metrics": {"operation_count": 1, "operations_by_type": {"tool": 1}},
        },
    ]
    summary = summarize_task_results(rows)
    assert summary["per_harness"]["h1"]["pass_rate"] == 0.5
    assert summary["per_harness"]["h1"]["operations_by_type"] == {"tool": 2, "loop": 1}


# ── paired binary significance (McNemar) on the execution-verified track ─────


def _row(task, harness, passed, *, repeat=1, error=None):
    metrics = {"operation_count": 0, "operations_by_type": {}}
    if error:
        metrics["error"] = error
    return {"task": task, "harness": harness, "passed": passed, "reward": None if error else float(passed),
            "elapsed_sec": 1.0, "repeat": repeat, "metrics": metrics}


def _sweep(pairs, *, baseline="noskill", treatment="skill"):
    """One row per task for both harnesses; ``pairs`` is [(base, treat), ...]."""
    rows = []
    for i, (base, treat) in enumerate(pairs):
        rows.append(_row(f"t{i}", baseline, base))
        rows.append(_row(f"t{i}", treatment, treat))
    return summarize_task_results(rows, baseline_harness=baseline)


def test_comparison_carries_a_paired_binary_test():
    # Six tasks the skill fixes, four both arms already solve.
    summary = _sweep([(False, True)] * 6 + [(True, True)] * 4)
    mc = summary["comparisons"]["skill"]["mcnemar"]
    assert mc["test"] == "mcnemar_exact"
    assert mc["n"] == 10
    assert mc["n_gained"] == 6 and mc["n_lost"] == 0
    assert mc["n_both_passed"] == 4
    assert mc["p_exact"] < 0.05
    assert mc["significant"] is True
    assert mc["significant_adjusted"] is True


def test_baseline_harness_is_not_compared_against_itself():
    summary = _sweep([(False, True)] * 6)
    assert "noskill" not in summary["comparisons"]


def test_no_pairing_without_a_baseline_harness():
    rows = [_row("t0", "skill", True), _row("t0", "noskill", False)]
    assert summarize_task_results(rows)["comparisons"] == {}


def test_harness_errors_are_excluded_rather_than_counted_as_failures():
    """A docker crash is missing data; charging it to the treatment would lie."""
    rows = [
        _row("t0", "noskill", False), _row("t0", "skill", True),
        _row("t1", "noskill", False), _row("t1", "skill", True),
        _row("t2", "noskill", False),
        _row("t2", "skill", False, error="RuntimeError: docker build failed"),
    ]
    mc = summarize_task_results(rows, baseline_harness="noskill")["comparisons"]["skill"]["mcnemar"]
    assert mc["n"] == 2                 # t2 dropped, not scored as a loss
    assert mc["n_gained"] == 2 and mc["n_lost"] == 0
    assert mc["n_excluded"] == 1


def test_cells_that_errored_on_both_sides_are_counted_as_excluded():
    """The loss is largest exactly where the old count reported zero.

    Measuring exclusions against the *surviving* cells missed any cell that
    errored on both sides, so a sweep where docker was broken for half the tasks
    reported ``n_excluded == 0`` and looked like a clean comparison.
    """
    rows = [
        _row("t0", "noskill", False), _row("t0", "skill", True),
        _row("t1", "noskill", False), _row("t1", "skill", True),
        _row("t2", "noskill", False, error="RuntimeError: docker build failed"),
        _row("t2", "skill", False, error="RuntimeError: docker build failed"),
    ]
    mc = summarize_task_results(rows, baseline_harness="noskill")["comparisons"]["skill"]["mcnemar"]
    assert mc["n"] == 2
    assert mc["n_excluded"] == 1


def test_repeats_pair_by_index_within_a_task():
    rows = [
        _row("t0", "noskill", False, repeat=1), _row("t0", "skill", True, repeat=1),
        _row("t0", "noskill", True, repeat=2), _row("t0", "skill", True, repeat=2),
    ]
    mc = summarize_task_results(rows, baseline_harness="noskill")["comparisons"]["skill"]["mcnemar"]
    assert mc["n"] == 2
    assert mc["n_gained"] == 1 and mc["n_both_passed"] == 1
    # Two pairs, but both are repeats of t0: one independent unit, and the
    # artifact has to say so rather than letting n stand in for sample size.
    assert mc["n_units"] == 1
    assert mc["pseudo_replicated"] is True


def test_one_repeat_per_task_is_not_flagged_as_pseudo_replicated():
    summary = _sweep([(False, True)] * 6)
    mc = summary["comparisons"]["skill"]["mcnemar"]
    assert mc["n_units"] == mc["n"] == 6
    assert mc["pseudo_replicated"] is False


def test_pvalues_are_corrected_across_the_compared_harnesses():
    rows = []
    for i in range(6):
        rows.append(_row(f"t{i}", "noskill", False))
        rows.append(_row(f"t{i}", "skill-a", True))
        rows.append(_row(f"t{i}", "skill-b", True))
    cmp = summarize_task_results(rows, baseline_harness="noskill")["comparisons"]
    for harness in ("skill-a", "skill-b"):
        mc = cmp[harness]["mcnemar"]
        assert mc["correction"] == "holm"
        assert mc["family_size"] == 2
        # Correction can only raise a p-value, never lower it.
        assert mc["p_adjusted"] >= mc["p_exact"]


def test_a_harness_with_no_shared_task_gets_no_test():
    rows = [_row("t0", "noskill", True), _row("t1", "skill", True)]
    cmp = summarize_task_results(rows, baseline_harness="noskill")["comparisons"]
    assert cmp["skill"]["mcnemar"] is None
    # The unpaired pass-rate delta is still reported; only the test is withheld.
    assert cmp["skill"]["pass_rate_delta"] == 0.0


def test_identical_outcomes_yield_no_verdict_rather_than_a_negative_one():
    summary = _sweep([(True, True), (False, False), (True, True)])
    mc = summary["comparisons"]["skill"]["mcnemar"]
    assert mc["n_discordant"] == 0
    assert mc["p_exact"] is None
    assert mc["significant"] is None
    assert mc["significant_adjusted"] is None


def test_a_real_mcnemar_block_validates_and_then_renders():
    """Schema-valid is not the same as renderable.

    Every other test on this track stops at the summary dict, so a formatter
    that raises on a field the runner really emits — a null ``p_exact``, the new
    ``pseudo_replicated`` caveat — would pass the suite. This runs the whole
    seam: real ``summarize_task_results`` output, validated, then rendered.
    """
    from agent_benchmarks.report.task_runs_report import render_task_runs_report

    rows = []
    for i in range(6):
        rows += [_row(f"t{i}", "noskill", False, repeat=1),
                 _row(f"t{i}", "skill", True, repeat=1),
                 _row(f"t{i}", "noskill", False, repeat=2),
                 _row(f"t{i}", "skill", True, repeat=2)]
    artifact = {
        "schema_version": "task_runs.v1",
        "generated_at": "2026-01-01T00:00:00Z",
        "model": "haiku",
        "baseline_harness": "noskill",
        "harnesses": ["noskill", "skill"],
        "repeats": 2,
        "tasks": [
            {"name": f"t{i}", "path": f"tasks/t{i}", "metadata": {"difficulty": "easy"},
             "verifier": {}, "agent": {}, "environment": {}}
            for i in range(6)
        ],
        "results": [{**r, "operations": []} for r in rows],
        "summary": summarize_task_results(rows, baseline_harness="noskill"),
    }
    validate_artifact("task_runs", artifact)

    md = render_task_runs_report(artifact)
    assert "## Paired significance vs baseline (McNemar)" in md
    # 12 pairs from 6 tasks: the caveat has to reach the reader, not just the JSON.
    assert "only 6 independent task(s)" in md
