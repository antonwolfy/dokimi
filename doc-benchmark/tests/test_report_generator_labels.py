"""Regression coverage for user-facing report terminology."""

from doc_benchmarks.report.generator import ReportGenerator


def test_report_generator_uses_context_arm_labels():
    eval_data = {
        "evaluations": [
            {
                "question_id": "q1",
                "question_text": "How to use parallel_for?",
                "category": "parallelism",
                "with_docs": {"aggregate": 80.0, "agreement_score": 0.9},
                "without_docs": {"aggregate": 60.0},
                "delta": 20.0,
            },
            {
                "question_id": "q2",
                "question_text": "How to avoid a scheduling mistake?",
                "category": "parallelism",
                "with_docs": {"aggregate": 40.0, "agreement_score": 0.9},
                "without_docs": {"aggregate": 70.0},
                "delta": -30.0,
            },
        ]
    }
    questions_data = {
        "questions": [
            {"id": "q1", "category": "parallelism", "source_type": "generated"},
            {"id": "q2", "category": "parallelism", "source_type": "generated"},
        ]
    }

    md = ReportGenerator().generate_report(
        eval_data,
        questions_data,
        multirun_with_averages=[60.0, 61.0, 60.5],
    )

    assert "Context Arm" in md
    assert "Baseline" in md
    assert "context hurt most" in md
    assert "Context-arm avg" in md
    assert ("WITH" + " | " + "WITHOUT") not in md
    assert ("WITH" + " Avg") not in md
    assert ("WITHOUT" + " Avg") not in md
    assert ("WITH" + "-docs") not in md
