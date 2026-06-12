"""Tests for multi-model comparison scripts."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import compare_models
from scripts import compare_models_combined


def _run(question_ids):
    evaluations = []
    for idx, qid in enumerate(question_ids, start=1):
        evaluations.append(
            {
                "question_id": qid,
                "question_text": f"Question {qid}",
                "difficulty": "medium",
                "scores": {
                    "baseline": {"aggregate": 50 + idx},
                    "skill:dpnp": {"aggregate": 60 + idx},
                },
            }
        )
    return {
        "model": "m",
        "provider": "p",
        "baseline_arm": "baseline",
        "evaluations": evaluations,
    }


def test_extract_scores_skips_invalid_arm_shapes():
    assert compare_models.extract_scores({"evaluations": []}) == []
    assert compare_models.extract_scores({"baseline_arm": 123, "evaluations": []}) == []
    assert (
        compare_models.extract_scores(
            {
                "baseline_arm": "baseline",
                "evaluations": [{"question_id": "q1", "scores": {"skill": {"aggregate": 1}}}],
            }
        )
        == []
    )


def test_generate_section_report_uses_common_questions_and_context_labels():
    lines = compare_models.generate_section_report(
        [("run-a", _run(["q1", "q2"])), ("run-b", _run(["q1"]))],
        ["run-a", "run-b"],
        "Regular",
    )
    text = "\n".join(lines)

    assert "Common questions evaluated: **1**" in text
    assert "| **run-a** | 1 |" in text
    assert "## Context-Arm Benefit — Delta Comparison" in text
    assert "Delta Comparison" in text
    assert "Baseline vs treatment" not in text


def test_load_run_reports_missing_file():
    with pytest.raises(SystemExit, match="File not found"):
        compare_models.load_run("does-not-exist.json")


def test_combined_runner_uses_absolute_script_and_typed_run_flag(monkeypatch, tmp_path):
    out = tmp_path / "sub.md"
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        out.write_text("## Models Compared\nbody", encoding="utf-8")
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(compare_models_combined.subprocess, "run", fake_run)

    content = compare_models_combined.run_compare_models(["a.json"], "a", out, "golden")

    assert content.startswith("## Models Compared")
    assert captured["cmd"][1] == str(compare_models_combined.COMPARE_MODELS_SCRIPT)
    assert Path(captured["cmd"][1]).is_absolute()
    assert "--golden-runs" in captured["cmd"]
    assert "--runs" not in captured["cmd"]


def test_combined_runner_raises_on_subprocess_failure(monkeypatch, tmp_path):
    def fake_run(cmd, **kwargs):
        return SimpleNamespace(returncode=2, stderr="bad args")

    monkeypatch.setattr(compare_models_combined.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="exit code 2"):
        compare_models_combined.run_compare_models(["a.json"], "a", tmp_path / "out.md", "regular")
