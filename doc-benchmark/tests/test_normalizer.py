"""Tests for questions/normalizer.py."""

import pytest
from doc_benchmarks.questions.normalizer import (
    normalize_question,
    normalize_questions,
    _normalize_difficulty,
)


# ── _normalize_difficulty ─────────────────────────────────────────────────────

@pytest.mark.parametrize("value,expected", [
    (1, "beginner"),
    (2, "intermediate"),
    (3, "advanced"),
    ("1", "beginner"),
    ("2", "intermediate"),
    ("3", "advanced"),
    ("beginner", "beginner"),
    ("intermediate", "intermediate"),
    ("advanced", "advanced"),
    ("easy", "beginner"),
    ("medium", "intermediate"),
    ("hard", "advanced"),
    ("expert", "advanced"),
    ("BEGINNER", "beginner"),   # case-insensitive fallback
    (None, "intermediate"),     # default
    ("unknown", "intermediate"),# unknown → default
])
def test_normalize_difficulty(value, expected):
    assert _normalize_difficulty(value) == expected


# ── normalize_question ────────────────────────────────────────────────────────

def test_normalize_question_canonical_fields():
    q = {"id": "q1", "question": "How to use TBB?", "difficulty": 2,
         "persona": "developer", "category": "api_reference", "expected_topics": ["parallel_for"]}
    result = normalize_question(q)
    assert result["id"] == "q1"
    assert result["question"] == "How to use TBB?"
    assert result["difficulty"] == "intermediate"
    assert result["persona"] == "developer"
    assert result["category"] == "api_reference"
    assert result["expected_topics"] == ["parallel_for"]


def test_normalize_question_text_fallback():
    """Legacy 'text' field should map to 'question'."""
    q = {"id": "q2", "text": "What is work-stealing?", "difficulty": 3}
    result = normalize_question(q)
    assert result["question"] == "What is work-stealing?"
    assert result["difficulty"] == "advanced"


def test_normalize_question_id_fallback():
    """If no 'id', falls back to question_id, then positional idx."""
    q = {"question_id": "qx", "text": "q?", "difficulty": 1}
    assert normalize_question(q)["id"] == "qx"

    q2 = {"text": "q?", "difficulty": 1}
    assert normalize_question(q2, idx=7)["id"] == "q0007"


def test_normalize_question_missing_optional_fields():
    """Missing optional fields default to empty string / list."""
    q = {"text": "Something?", "difficulty": 2}
    result = normalize_question(q)
    assert result["persona"] == ""
    assert result["category"] == ""
    assert result["expected_topics"] == []


def test_normalize_question_numeric_difficulty_all_levels():
    for num, label in [(1, "beginner"), (2, "intermediate"), (3, "advanced")]:
        assert normalize_question({"text": "q?", "difficulty": num})["difficulty"] == label


# ── normalize_questions ───────────────────────────────────────────────────────

def test_normalize_questions_batch():
    questions = [
        {"id": f"q{i}", "text": f"Question {i}?", "difficulty": (i % 3) + 1}
        for i in range(6)
    ]
    results = normalize_questions(questions)
    assert len(results) == 6
    assert all("question" in r for r in results)
    assert all(r["difficulty"] in ("beginner", "intermediate", "advanced") for r in results)


def test_normalize_questions_preserves_order():
    questions = [{"text": f"Q{i}", "difficulty": 1} for i in range(10)]
    results = normalize_questions(questions)
    for i, r in enumerate(results):
        assert r["question"] == f"Q{i}"


def test_normalize_questions_empty():
    assert normalize_questions([]) == []
