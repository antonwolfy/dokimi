"""Tests for artifact -> dataset export."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from doc_benchmarks.datasets_export import dataset_card, export_artifact, flatten

HAS_DATASETS = importlib.util.find_spec("datasets") is not None


def test_flatten_attaches_metadata_and_jsonifies():
    data = {
        "schema_version": "answers.v1",
        "model": "gpt-4o",
        "answers": [
            {"question_id": "q1", "with_docs": {"answer": "a", "model": "gpt-4o"}},
        ],
    }
    rows = flatten("answers", data)
    assert rows[0]["model"] == "gpt-4o"
    assert rows[0]["question_id"] == "q1"
    # nested dict is JSON-encoded
    assert json.loads(rows[0]["with_docs"])["answer"] == "a"


def test_export_jsonl(tmp_path):
    src = tmp_path / "q.json"
    src.write_text(json.dumps({
        "schema_version": "questions.v1",
        "library": "oneTBB",
        "questions": [{"id": "q1", "text": "What is X?"}, {"id": "q2", "text": "How Y?"}],
    }))
    out = tmp_path / "out"
    primary = export_artifact("questions", src, out, fmt="jsonl")
    assert primary.exists()
    lines = primary.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["library"] == "oneTBB"
    assert (out / "README.md").exists()


def test_export_real_fixture_jsonl(tmp_path):
    fixture = Path(__file__).resolve().parents[1] / "answers" / "onetbb.json"
    if not fixture.exists():
        pytest.skip("fixture missing")
    primary = export_artifact("answers", fixture, tmp_path / "out", fmt="jsonl")
    assert primary.exists()
    assert primary.read_text().strip()


def test_dataset_card_contents():
    card = dataset_card("questions", Path("questions/onetbb.json"), 5, ["id", "text"])
    assert "questions.v1" in card
    assert "Rows:** 5" in card


@pytest.mark.skipif(not HAS_DATASETS, reason="datasets not installed")
def test_export_parquet(tmp_path):
    src = tmp_path / "q.json"
    src.write_text(json.dumps({"schema_version": "questions.v1",
                               "questions": [{"id": "q1", "text": "x"}]}))
    primary = export_artifact("questions", src, tmp_path / "out", fmt="parquet")
    assert primary.exists()


def test_flatten_missing_record_key_raises():
    import pytest
    with pytest.raises(KeyError):
        flatten("answers", {"not_answers": []})


def test_flatten_non_list_records_raises():
    import pytest
    with pytest.raises(TypeError):
        flatten("answers", {"answers": {"q": 1}})
