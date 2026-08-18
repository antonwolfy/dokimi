"""Tests for agent_benchmarks.report.model_compare (package module)."""

from __future__ import annotations

import json

import pytest

from agent_benchmarks.report.model_compare import (
    check_run_consistency,
    extract_scores,
    generate_combined_report,
    generate_section_report,
    load_run,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _eval_run(questions: list[dict], baseline: str = "baseline", **meta) -> dict:
    """Build a minimal arms artifact with the evaluations format."""
    evaluations = []
    for q in questions:
        evaluations.append(
            {
                "question_id": q["id"],
                "question_text": q.get("text", ""),
                "category": q.get("category", ""),
                "difficulty": q.get("difficulty", "easy"),
                "persona": q.get("persona", ""),
                "scores": q.get("scores", {}),
            }
        )
    data: dict = {
        "baseline_arm": baseline,
        "model": meta.get("model", "model-x"),
        "provider": meta.get("provider", "prov"),
        "evaluations": evaluations,
    }
    if "question_set_hash" in meta:
        data["question_set_hash"] = meta["question_set_hash"]
    return data


def _q(qid: str, baseline_score=60, treatment_score=80, arm="with-context", **kw) -> dict:
    return {
        "id": qid,
        "scores": {"baseline": {"aggregate": baseline_score}, arm: {"aggregate": treatment_score}},
        **kw,
    }


# ---------------------------------------------------------------------------
# load_run
# ---------------------------------------------------------------------------


def test_load_run_valid(tmp_path):
    p = tmp_path / "run.json"
    p.write_text(json.dumps({"baseline_arm": "baseline"}), encoding="utf-8")
    data = load_run(str(p))
    assert data["baseline_arm"] == "baseline"


def test_load_run_missing_file():
    with pytest.raises(SystemExit, match="File not found"):
        load_run("/nonexistent/path/run.json")


def test_load_run_invalid_json(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not valid json}", encoding="utf-8")
    with pytest.raises(SystemExit, match="Invalid JSON"):
        load_run(str(p))


# ---------------------------------------------------------------------------
# check_run_consistency
# ---------------------------------------------------------------------------


def _run_pair(run_id, **kw):
    return (run_id, {"baseline_arm": kw.get("baseline", "baseline"),
                     "model": kw.get("model", "m"), "provider": kw.get("provider", "p"),
                     **({} if "q_hash" not in kw else {"question_set_hash": kw["q_hash"]})})


def test_consistency_single_run_no_warnings():
    assert check_run_consistency([_run_pair("a")], "g") == []


def test_consistency_baseline_mismatch_raises():
    with pytest.raises(SystemExit, match="different baseline_arm"):
        check_run_consistency(
            [_run_pair("a", baseline="no-context"), _run_pair("b", baseline="baseline")], "g"
        )


def test_consistency_hash_mismatch_warns():
    runs = [_run_pair("a", model="m1", q_hash="aaaa"), _run_pair("b", model="m2", q_hash="bbbb")]
    warns = check_run_consistency(runs, "g")
    assert any("question_set_hash" in w for w in warns)


def test_consistency_identical_model_warns():
    runs = [_run_pair("a", model="same"), _run_pair("b", model="same")]
    warns = check_run_consistency(runs, "g")
    assert any("same model" in w for w in warns)


def test_consistency_ok_different_models():
    runs = [_run_pair("a", model="m1"), _run_pair("b", model="m2")]
    assert check_run_consistency(runs, "g") == []


# ---------------------------------------------------------------------------
# extract_scores — partial / failed evaluations
# ---------------------------------------------------------------------------


def test_extract_scores_keeps_records_with_missing_aggregate():
    """Records are kept with None so the common-question intersection survives."""
    run = _eval_run([
        {"id": "Q1", "scores": {"baseline": {"aggregate": 60}, "with-ctx": {"aggregate": 80}}},
        {"id": "Q2", "scores": {"baseline": {}, "with-ctx": {"aggregate": 70}}},
        {"id": "Q3", "scores": {"baseline": {"aggregate": 50}, "with-ctx": {}}},
    ])
    scores = extract_scores(run)
    assert [s["question_id"] for s in scores] == ["Q1", "Q2", "Q3"]

    assert scores[0]["without_docs"] == 60
    assert scores[0]["with_docs"] == 80
    assert scores[0]["delta"] == 20

    # Missing baseline: carried as None rather than 0.0, which would inflate the
    # delta, and rather than dropped, which would shrink the intersection.
    assert scores[1]["without_docs"] is None
    assert scores[1]["with_docs"] == 70
    assert scores[1]["delta"] is None

    assert scores[2]["without_docs"] == 50
    assert scores[2]["with_docs"] is None
    assert scores[2]["delta"] is None


def test_missing_baseline_run_does_not_empty_the_intersection():
    """A run with no usable baselines must not zero out N for every other run."""
    good = _eval_run([_q("Q1"), _q("Q2")], model="good")
    broken = _eval_run([
        {"id": "Q1", "scores": {"baseline": {"error": "boom"}, "with-context": {"aggregate": 70}}},
        {"id": "Q2", "scores": {"baseline": {"error": "boom"}, "with-context": {"aggregate": 72}}},
    ], model="broken")

    lines = "\n".join(
        generate_section_report([("good", good), ("broken", broken)], ["good", "broken"], "test")
    )
    assert "Common questions evaluated: **2**" in lines


def _scored(qid, baseline, treatment, arm="with-context"):
    """Question spec allowing either side to be an error instead of a score."""
    return {
        "id": qid,
        "scores": {
            "baseline": {"aggregate": baseline} if baseline is not None else {"error": "boom"},
            arm: {"aggregate": treatment} if treatment is not None else {"error": "boom"},
        },
    }


def test_no_usable_score_renders_dash_not_zero():
    """An arm with no score must not print as 0, which reads as a real 0/100."""
    ok = _eval_run([_scored("Q1", 70, 75), _scored("Q2", 72, 78)], model="ok")
    bad = _eval_run([_scored("Q1", None, 75), _scored("Q2", None, 78)], model="bad")

    lines = "\n".join(generate_section_report([("ok", ok), ("bad", bad)], ["ok", "bad"], "t"))
    bad_row = next(ln for ln in lines.splitlines() if ln.startswith("| **bad** |") and "unscored" in ln)
    assert "| 0.0 |" not in bad_row
    assert "—" in bad_row


def test_by_difficulty_uses_paired_delta():
    """By-difficulty must not difference independently filtered means either."""
    # Q2 has a treatment score but no baseline. Differencing means gives +13.3;
    # the paired mean over Q1 and Q3 is +7.5.
    run = _eval_run([
        _scored("Q1", 70, 80),
        _scored("Q2", None, 90),
        _scored("Q3", 60, 65),
    ])
    lines = generate_section_report([("a", run)], ["a"], "t")
    diff_row = next(ln for ln in lines if ln.startswith("| easy |"))
    assert "+7.5" in diff_row
    assert "+13.3" not in diff_row


def test_difficulty_row_matches_header_column_count():
    """Runs differing in treatment coverage must not desync header and row widths."""
    ok = _eval_run([_scored("Q1", 70, 75), _scored("Q2", 72, 78)], model="ok")
    # No treatment score at all: previously flipped the header into baseline mode
    # via a clobbered has_treatment while rows still emitted two cells per run.
    bad = _eval_run([_scored("Q1", 70, None), _scored("Q2", 72, None)], model="bad")

    lines = generate_section_report([("ok", ok), ("bad", bad)], ["ok", "bad"], "t")
    header = next(ln for ln in lines if ln.startswith("| Difficulty |"))
    row = next(ln for ln in lines if ln.startswith("| easy |"))
    assert header.count("|") == row.count("|")


def test_delta_avg_is_mean_of_paired_deltas():
    """Delta must be the paired mean, not the difference of independently filtered means."""
    # Q2 has a treatment score but no baseline. Differencing arm means would give
    # (80+90)/2 - 60 = +25; the paired mean over Q1 alone is +20.
    run = _eval_run([
        {"id": "Q1", "scores": {"baseline": {"aggregate": 60}, "with-ctx": {"aggregate": 80}}},
        {"id": "Q2", "scores": {"baseline": {}, "with-ctx": {"aggregate": 90}}},
    ])
    lines = "\n".join(generate_section_report([("a", run)], ["a"], "test"))
    assert "**+20.0**" in lines
    assert "1 (1 unscored)" in lines


def test_extract_scores_skips_missing_question_id():
    run = _eval_run([
        {"id": "", "scores": {"baseline": {"aggregate": 60}, "with-ctx": {"aggregate": 80}}},
        {"id": "Q1", "scores": {"baseline": {"aggregate": 60}, "with-ctx": {"aggregate": 80}}},
    ])
    scores = extract_scores(run)
    assert len(scores) == 1
    assert scores[0]["question_id"] == "Q1"


def test_extract_scores_empty_evaluations():
    run = {"baseline_arm": "baseline", "evaluations": []}
    assert extract_scores(run) == []


def test_extract_scores_no_baseline_arm_returns_empty():
    run = {"evaluations": [{"question_id": "Q1", "scores": {"baseline": {"aggregate": 60}}}]}
    assert extract_scores(run) == []


def test_extract_scores_skips_question_where_baseline_absent_from_scores():
    """baseline_arm is set on the run but a specific question's scores dict
    doesn't contain that key at all — question must be silently skipped."""
    run = _eval_run([
        {"id": "Q1", "scores": {"skill:dpnp": {"aggregate": 70}}},  # no "baseline" key
        {"id": "Q2", "scores": {"baseline": {"aggregate": 50}, "skill:dpnp": {"aggregate": 70}}},
    ])
    scores = extract_scores(run)
    assert len(scores) == 1
    assert scores[0]["question_id"] == "Q2"


def test_extract_scores_all_failed_yields_no_usable_scores():
    """Every score None: records are kept for the intersection, but nothing is scored."""
    run = _eval_run([
        {"id": "Q1", "scores": {"baseline": {"aggregate": None}, "arm": {"aggregate": None}}},
        {"id": "Q2", "scores": {"baseline": {}, "arm": {}}},
    ])
    scores = extract_scores(run)
    assert [s["question_id"] for s in scores] == ["Q1", "Q2"]
    assert all(s["without_docs"] is None for s in scores)
    assert all(s["with_docs"] is None for s in scores)
    assert all(s["delta"] is None for s in scores)


def test_extract_scores_partial_coverage_diagnostic(capsys):
    """extract_scores should not crash on partial evaluations; missing questions
    surface as a smaller common-question set in the section report."""
    run_a = _eval_run([_q("Q1"), _q("Q2"), _q("Q3")], model="a")
    run_b = _eval_run([_q("Q1"), _q("Q3")], model="b")  # Q2 missing

    lines = generate_section_report([(("a", run_a)), ("b", run_b)], ["a", "b"], "test")
    # Common questions should be 2, not 3
    assert "Common questions evaluated: **2**" in "\n".join(lines)


# ---------------------------------------------------------------------------
# generate_section_report — end-to-end smoke
# ---------------------------------------------------------------------------


def test_section_report_basic_output():
    run_a = _eval_run([_q("Q1", 60, 80), _q("Q2", 50, 70)], model="m-a")
    run_b = _eval_run([_q("Q1", 55, 75), _q("Q2", 45, 65)], model="m-b")
    lines = generate_section_report([("a", run_a), ("b", run_b)], ["a", "b"], "Regular")
    text = "\n".join(lines)
    assert "## Models Compared" in text
    assert "## Overall Summary" in text
    assert "## Head-to-Head" in text
    assert "Common questions evaluated: **2**" in text


def test_generate_combined_report_writes_file(tmp_path):
    run_a = _eval_run([_q("Q1"), _q("Q2")], model="m-a")
    run_b = _eval_run([_q("Q1"), _q("Q2")], model="m-b")
    out = tmp_path / "report.md"
    generate_combined_report([("a", run_a), ("b", run_b)], [], ["a", "b"], str(out))
    assert out.exists()
    content = out.read_text()
    assert "Model Comparison Report" in content
    assert "## Overall Summary" in content
