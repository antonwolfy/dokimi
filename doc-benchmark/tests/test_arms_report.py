"""Tests for the arms-comparison Markdown report."""

from doc_benchmarks.report.arms_report import render_arms_report, _md_cell


def test_md_cell_escapes_pipes_and_newlines():
    assert _md_cell("a | b\nc") == r"a \| b c"
    assert _md_cell(None) == ""


def test_report_escapes_question_text_in_table():
    data = {
        "library_name": "oneTBB",
        "model": "m", "provider": "openai",
        "arms": ["baseline"],
        "baseline_arm": "baseline",
        "total_questions": 1,
        "answers": [],
        "evaluations": [
            {"question_text": "What | how\nnewline?",
             "scores": {"baseline": {"aggregate": 70}}}
        ],
        "summary": {"per_arm": {"baseline": {"avg_aggregate": 70.0, "n": 1}}},
    }
    md = render_arms_report(data)
    # The raw pipe inside the question must be escaped so the row stays valid.
    assert r"What \| how" in md
    assert "What | how\nnewline" not in md


def test_report_renders_agentic_section():
    data = {
        "library_name": "oneTBB", "model": "m", "provider": "openai",
        "arms": ["agent"], "baseline_arm": "baseline", "total_questions": 1,
        "answers": [
            {"arms": {"agent": {"agentic": True, "tool_call_count": 2, "iterations": 3}}}
        ],
    }
    md = render_arms_report(data)
    assert "Agentic tool use" in md
    assert "`agent`" in md
