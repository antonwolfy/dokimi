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
        ("answers", REPO / "data" / "answers" / "onetbb.json"),
        ("eval", REPO / "data" / "eval" / "onetbb.json"),
    ]
    for kind, path in cases:
        assert path.exists(), f"missing committed fixture: {path}"
        load_artifact(kind, path)  # raises on failure


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
