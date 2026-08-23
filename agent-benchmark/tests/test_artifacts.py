"""Tests for versioned, schema-validated artifact I/O."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_benchmarks.artifacts import (
    SCHEMA_VERSIONS,
    ArtifactValidationError,
    load_artifact,
    save_artifact,
    stamp,
    validate_artifact,
)

REPO = Path(__file__).resolve().parents[1]


def test_all_kinds_have_schema_files():
    for kind, version in SCHEMA_VERSIONS.items():
        schema = REPO / "agent_benchmarks" / "schemas" / f"{version}.json"
        assert schema.exists(), f"missing schema for {kind}: {schema}"


def test_committed_fixtures_validate():
    """Real committed fixtures must satisfy their schemas (locks the contract)."""
    cases = [
        ("questions", REPO / "data" / "questions" / "onetbb.json"),
        ("questions", REPO / "data" / "questions" / "onedal.json"),
        ("questions", REPO / "data" / "questions" / "intel_performance_skills_golden.json"),
        ("answers", REPO / "data" / "answers" / "onetbb.json"),
        ("eval", REPO / "data" / "eval" / "onetbb.json"),
    ]
    for kind, path in cases:
        assert path.exists(), f"missing committed fixture: {path}"
        load_artifact(kind, path)  # raises on failure


def test_perf_golden_level_backfill():
    """Lock the difficulty/level two-axis rubric on the perf golden set.

    Every question carries a ``level`` from the schema enum, and the
    ``negative_case`` flag (when present) is the boolean ``True`` convention
    documented in docs/difficulty-rubric.md.
    """
    path = REPO / "data" / "questions" / "intel_performance_skills_golden.json"
    data = load_artifact("questions", path)
    questions = data["questions"]
    valid_levels = {"triage", "diagnosis", "end_to_end"}
    for q in questions:
        assert q.get("level") in valid_levels, f"{q.get('id')}: bad/missing level {q.get('level')!r}"
        flag = q.get("metadata", {}).get("negative_case")
        assert flag in (None, True), f"{q.get('id')}: negative_case must be true or absent, got {flag!r}"


def test_stamp_sets_version():
    data = stamp("questions", {"questions": []})
    assert data["schema_version"] == "questions.v1"


def test_save_roundtrip_stamps_and_validates(tmp_path):
    out = tmp_path / "q.json"
    save_artifact("questions", {"questions": [{"id": "q1", "text": "What is X?"}]}, out)
    loaded = load_artifact("questions", out)
    assert loaded["schema_version"] == "questions.v1"
    assert loaded["questions"][0]["id"] == "q1"


def test_save_rejects_invalid(tmp_path):
    with pytest.raises(ArtifactValidationError):
        save_artifact("answers", {"not_answers": []}, tmp_path / "bad.json")


def test_validate_missing_required_field():
    with pytest.raises(ArtifactValidationError, match="evaluations"):
        validate_artifact("eval", {"evaluated_at": "now"})


def test_question_item_requires_text():
    with pytest.raises(ArtifactValidationError):
        validate_artifact("questions", {"questions": [{"id": "q1"}]})


def test_unknown_kind_raises():
    with pytest.raises(KeyError):
        validate_artifact("nope", {})


def test_arms_schema_accepts_built_output():
    out = {
        "arms": ["baseline", "with_docs"],
        "answers": [],
        "summary": {"per_arm": {"baseline": {"avg_aggregate": 70.0, "n": 3}}},
    }
    validate_artifact("arms", out)


def test_save_does_not_mutate_caller():
    data = {"questions": [{"id": "q1", "text": "x"}]}
    import tempfile, os
    with tempfile.TemporaryDirectory() as d:
        save_artifact("questions", data, os.path.join(d, "q.json"))
    assert "schema_version" not in data  # caller dict untouched


def test_schema_version_const_rejects_wrong_value():
    with pytest.raises(ArtifactValidationError):
        validate_artifact("questions", {"schema_version": "questions.v2", "questions": []})


def _factorial_summary():
    """Real ``_summarize`` output for a 2x2 design, so the schema is checked
    against what the runner actually emits rather than a hand-written stub."""
    from agent_benchmarks.eval.arm_runner import ArmRunner
    from agent_benchmarks.treatments import BaselineTreatment

    arms = ["baseline", "docs", "skill:x", "docs+skill:x"]
    base = [50, 52, 48, 51, 49, 53]
    jitter = [1, -1, 2, -2, 1, -1]
    evaluations = [
        {
            "question_id": f"q{i}",
            "scores": {
                "baseline": {"aggregate": b},
                "docs": {"aggregate": b + 2 + j},
                "skill:x": {"aggregate": b + 12 - j},
                "docs+skill:x": {"aggregate": b + 6 + j},
            },
        }
        for i, (b, j) in enumerate(zip(base, jitter, strict=True))
    ]
    runner = ArmRunner([BaselineTreatment(name) for name in arms])
    return arms, runner._summarize(evaluations, "baseline")


def test_arms_schema_accepts_significance_and_interactions():
    arms, summary = _factorial_summary()
    assert summary["per_arm"]["docs"]["significance"]["correction"] == "holm"
    assert len(summary["interactions"]) == 1
    validate_artifact("arms", {"arms": arms, "answers": [], "summary": summary})


def test_real_factorial_output_validates_and_then_renders():
    """Schema-valid is not the same as renderable.

    Every other stats test stops at ``validate_artifact``, so a formatter that
    raises on a field the runner really emits — a ``None`` Cohen's d_z, a
    missing adjusted verdict — would pass the suite. This runs the whole seam:
    real ``_summarize`` output, validated, then rendered to Markdown.
    """
    from agent_benchmarks.report.arms_report import render_arms_report

    arms, summary = _factorial_summary()
    artifact = {
        "library_name": "onetbb", "model": "m", "provider": "openai",
        "arms": arms, "baseline_arm": "baseline", "total_questions": 6,
        "answers": [], "summary": summary,
    }
    validate_artifact("arms", artifact)
    md = render_arms_report(artifact)
    assert "## Paired significance vs baseline" in md
    assert "## Factorial interaction" in md
    # Both families name themselves, so a reader can tell what was corrected
    # together rather than assuming one pooled correction.
    assert "treatment arm(s)" in md and "interaction contrast(s)" in md


def test_arms_schema_still_accepts_artifact_without_stats():
    """Pre-existing arms.v1 artifacts predate these keys and must stay valid."""
    validate_artifact("arms", {
        "arms": ["baseline", "docs"],
        "answers": [],
        "summary": {"per_arm": {"docs": {"avg_aggregate": 70.0, "n": 3,
                                        "delta_vs_baseline": 4.0}}},
    })


def test_arms_schema_rejects_bad_effect_label():
    """The new block is constrained, not merely documented."""
    with pytest.raises(ArtifactValidationError):
        validate_artifact("arms", {
            "arms": ["baseline", "docs"],
            "answers": [],
            "summary": {"per_arm": {"docs": {"significance": {"effect": "enormous"}}}},
        })


def test_arms_schema_rejects_bad_correction_name():
    with pytest.raises(ArtifactValidationError):
        validate_artifact("arms", {
            "arms": ["baseline", "docs"],
            "answers": [],
            "summary": {"per_arm": {"docs": {"significance": {"correction": "bonferroni"}}}},
        })


def test_arms_schema_rejects_non_array_interactions():
    with pytest.raises(ArtifactValidationError):
        validate_artifact("arms", {
            "arms": ["baseline", "docs"],
            "answers": [],
            "summary": {"interactions": {"interaction": -8.0}},
        })
