"""Tests for the judge-validity gate and the degradations it relies on.

These run offline. What is covered here is the harness — that degradations
really damage an answer, that they are reproducible, and that the accuracy and
gate arithmetic is right for judges whose behaviour is known (a perfect judge, a
saturated judge, an inverted judge). Measuring a real LLM judge needs API
credentials and is the job of `cli.py eval judge-validity`.
"""

import pytest

from agent_benchmarks.eval.degrade import (
    DEGRADATIONS,
    build_pairs,
    degrade,
    strip_code,
    truncate_20,
    wrong_tools,
)
from agent_benchmarks.eval.judge_validity import (
    DEFAULT_MIN_ACCURACY,
    ValidityRow,
    evaluate_pairs,
    run_validity,
)

ANSWER = (
    "Use perf stat to collect IPC on the Intel platform, then narrow the hotspot "
    "with VTune. The oneTBB scheduler is not the bottleneck here.\n\n"
    "```\nperf stat -e cycles,instructions ./app\n```\n\n"
    "Once you have the PMU counters, enable AVX-512 in the build. "
) * 12

# Also long, also fenced, also full of tool names — so every degradation bites
# on it too. An answer with no code and no tool mentions is a silent no-op for
# strip_code and wrong_tools, which would make the fixtures lie.
OTHER_ANSWER = (
    "Install the Intel oneAPI toolkit first, then check the PMU is exposed.\n\n"
    "```\napt install intel-oneapi-base\n```\n\n"
    "VTune needs perf_event_paranoid lowered before it can read IPC. "
) * 12


def _answers():
    return [
        {
            "question_id": "Q001",
            "question_text": "How do I find the hotspot?",
            "arms": {
                "baseline": {"answer": ANSWER},
                "skill": {"answer": ANSWER + "Extra detail. "},
            },
        },
        {
            "question_id": "Q002",
            "question_text": "How do I install it?",
            "arms": {"baseline": {"answer": OTHER_ANSWER}},
        },
    ]


class TestDegradations:
    def test_truncate_keeps_a_fifth(self):
        out = truncate_20(ANSWER)
        assert len(out) < len(ANSWER)
        assert ANSWER.startswith(out)

    def test_strip_code_removes_fences(self):
        out = strip_code(ANSWER)
        assert "```" not in out
        assert "[code removed]" in out

    def test_wrong_tools_swaps_technology_but_keeps_length(self):
        out = wrong_tools(ANSWER)
        assert "gprof" in out and "perf stat" not in out
        assert "AMD" in out and "Intel" not in out
        assert "pthreads" in out and "oneTBB" not in out
        # The damage must be invisible to a length or structure heuristic.
        assert abs(len(out) - len(ANSWER)) < 0.2 * len(ANSWER)

    def test_shuffle_changes_order_not_content(self):
        out = degrade(ANSWER, "shuffle_sentences", seed=1)
        assert out != ANSWER
        assert "perf stat" in out

    def test_every_degradation_actually_changes_the_answer(self):
        for name in DEGRADATIONS:
            out = degrade(ANSWER, name, other=OTHER_ANSWER)
            assert out != ANSWER, name
            assert out, name

    def test_seeded_degradations_are_reproducible(self):
        for name in DEGRADATIONS:
            first = degrade(ANSWER, name, seed=7, other=OTHER_ANSWER)
            second = degrade(ANSWER, name, seed=7, other=OTHER_ANSWER)
            assert first == second, name

    def test_unknown_degradation_rejected(self):
        with pytest.raises(ValueError, match="Unknown degradation"):
            degrade(ANSWER, "not_a_variant")

    def test_mismatched_answer_needs_another_answer(self):
        with pytest.raises(ValueError, match="requires another answer"):
            degrade(ANSWER, "mismatched_answer")


class TestBuildPairs:
    def test_one_pair_per_base_and_variant(self):
        pairs = build_pairs(_answers(), n_bases=2, min_chars=100)
        assert len(pairs) == 2 * len(DEGRADATIONS)
        assert {p["variant"] for p in pairs} == set(DEGRADATIONS)
        for p in pairs:
            assert p["intact"] != p["degraded"]

    def test_short_answers_are_skipped(self):
        answers = [
            {"question_id": "Q1", "question_text": "q", "arms": {"baseline": {"answer": "short"}}}
        ]
        assert build_pairs(answers, min_chars=1000) == []

    def test_legacy_with_docs_shape_supported(self):
        answers = [
            {
                "question_id": "Q1",
                "question_text": "q",
                "with_docs": {"answer": ANSWER},
                "without_docs": {"answer": OTHER_ANSWER},
            }
        ]
        pairs = build_pairs(answers, min_chars=100)
        assert {p["arm"] for p in pairs} == {"with_docs", "without_docs"}

    def test_variant_selection_is_validated(self):
        with pytest.raises(ValueError, match="Unknown degradation"):
            build_pairs(_answers(), variants=["truncate_20", "nope"])

    def test_mismatched_variant_dropped_when_no_other_question(self):
        answers = [
            {"question_id": "Q1", "question_text": "q", "arms": {"baseline": {"answer": ANSWER}}}
        ]
        pairs = build_pairs(answers, min_chars=100)
        assert "mismatched_answer" not in {p["variant"] for p in pairs}


class TestValidityRow:
    @pytest.mark.parametrize(
        "intact,degraded,expected",
        [(90.0, 50.0, 1.0), (50.0, 90.0, 0.0), (90.0, 90.0, 0.5), (None, 90.0, None)],
    )
    def test_correct_counts_ties_as_half(self, intact, degraded, expected):
        row = ValidityRow("Q1", "baseline", "truncate_20", intact, degraded)
        assert row.correct == expected


class TestEvaluatePairs:
    @staticmethod
    def _pairs():
        # mismatched_answer is excluded here: its damaged copy IS another base's
        # intact answer, so a judge keyed on "is this text intact" cannot be
        # right about it by construction. That variant is covered above.
        return build_pairs(
            _answers(),
            n_bases=2,
            min_chars=100,
            variants=[v for v in DEGRADATIONS if v != "mismatched_answer"],
        )

    @classmethod
    def _oracle(cls, pairs, inverted=False):
        """A judge that knows exactly which text is the undamaged one."""
        intact = {p["intact"] for p in pairs}

        def score(lib, q, a):
            good = a in intact
            return (10.0 if good else 100.0) if inverted else (100.0 if good else 10.0)

        return score

    def test_perfect_judge_passes(self):
        pairs = self._pairs()
        report = evaluate_pairs(self._oracle(pairs), pairs, judge="oracle")
        summary = report.summary()
        assert summary["accuracy"] == 1.0
        assert summary["passed"] is True
        assert summary["n_errors"] == 0

    def test_saturated_judge_fails_on_ties_not_on_wrong_order(self):
        report = evaluate_pairs(lambda lib, q, a: 100.0, self._pairs(), judge="ceiling")
        summary = report.summary()
        assert summary["accuracy"] == 0.5
        assert summary["tie_rate"] == 1.0
        assert summary["passed"] is False

    def test_inverted_judge_fails(self):
        pairs = self._pairs()
        report = evaluate_pairs(self._oracle(pairs, inverted=True), pairs, judge="inverted")
        assert report.summary()["accuracy"] == 0.0
        assert report.summary()["passed"] is False

    def test_intact_answer_scored_once_per_base(self):
        calls = []

        def scorer(lib, q, a):
            calls.append(a)
            return float(len(a))

        pairs = self._pairs()
        evaluate_pairs(scorer, pairs, judge="counter")
        bases = len({(p["base_id"], p["arm"]) for p in pairs})
        # one intact score per base + one per degraded variant
        assert len(calls) == bases + len(pairs)

    def test_scorer_error_is_recorded_not_raised(self):
        def scorer(lib, q, a):
            if "gprof" in a:
                raise RuntimeError("boom")
            return float(len(a))

        report = evaluate_pairs(scorer, self._pairs(), judge="flaky")
        assert report.errors
        assert all("RuntimeError" in (r.error or "") for r in report.errors)
        # Errored pairs are excluded from the accuracy, not counted as correct.
        assert len(report.scored) == len(report.rows) - len(report.errors)

    def test_no_scored_pairs_is_a_failure(self):
        def scorer(lib, q, a):
            raise RuntimeError("no judge available")

        report = evaluate_pairs(scorer, self._pairs(), judge="dead")
        summary = report.summary()
        assert summary["n_pairs"] == 0
        assert summary["passed"] is False

    def test_per_variant_breakdown_reports_drop_and_ties(self):
        pairs = self._pairs()
        report = evaluate_pairs(lambda lib, q, a: float(len(a)), pairs, judge="length")
        per_variant = report.summary()["per_variant"]
        assert set(per_variant) == {p["variant"] for p in pairs}
        # A length judge sees truncation perfectly...
        assert per_variant["truncate_20"]["accuracy"] == 1.0
        assert per_variant["truncate_20"]["mean_drop"] > 0
        # ...but wrong_tools leaves the answer just as long, so a length judge
        # actively prefers the sabotaged copy: a negative drop is the judge
        # scoring the damaged answer higher.
        assert per_variant["wrong_tools"]["mean_drop"] < 0
        assert per_variant["wrong_tools"]["accuracy"] == 0.0
        for stats in per_variant.values():
            assert stats["n"] > 0
            assert 0.0 <= stats["accuracy"] <= 1.0

    def test_threshold_is_the_gate(self):
        pairs = self._pairs()
        strict = evaluate_pairs(lambda lib, q, a: 100.0, pairs, min_accuracy=0.9)
        lenient = evaluate_pairs(lambda lib, q, a: 100.0, pairs, min_accuracy=0.4)
        assert strict.summary()["passed"] is False
        assert lenient.summary()["passed"] is True

    def test_format_summary_states_the_verdict(self):
        report = evaluate_pairs(lambda lib, q, a: float(len(a)), self._pairs(), judge="length")
        text = report.format_summary()
        assert "Judge validity" in text
        assert "wrong_tools" in text
        assert ("PASS" in text) or ("FAIL" in text)


class TestRunValidity:
    def test_end_to_end_with_a_stub_judge(self):
        report = run_validity(
            _answers(),
            lambda lib, q, a: float(len(a)),
            judge="stub",
            n_bases=2,
            library="oneTBB",
        )
        assert report.summary()["n_pairs"] > 0
        assert report.summary()["min_accuracy"] == DEFAULT_MIN_ACCURACY

    def test_no_usable_answers_raises(self):
        with pytest.raises(ValueError, match="No usable answers"):
            run_validity([{"question_id": "Q1", "question_text": "q", "arms": {}}], lambda *a: 1.0)


@pytest.mark.parametrize("provider", ["openai", "anthropic", "google", "google-vertex", "openrouter", "amazon-bedrock"])
def test_judge_validity_accepts_every_judge_provider(provider):
    from agent_benchmarks.cli import build_parser

    args = build_parser().parse_args(["eval", "judge-validity", "--answers", "a.json", "--judge-provider", provider])
    assert args.judge_provider == provider


@pytest.mark.parametrize("provider", ["azure", "bedrock"])
def test_judge_validity_rejects_providers_judge_rejects(provider):
    from agent_benchmarks.cli import build_parser

    with pytest.raises(SystemExit):
        build_parser().parse_args(["eval", "judge-validity", "--answers", "a.json", "--judge-provider", provider])


def test_noop_degradation_is_dropped_and_counted():
    plain = [{"question_id": "Q9", "question_text": "Why?", "arms": {"a": {"answer": "no tools here. " * 200}}}]
    noop: dict = {}
    pairs = build_pairs(plain, variants=["wrong_tools", "truncate_20"], noop=noop)
    assert [p["variant"] for p in pairs] == ["truncate_20"]
    assert noop == {"wrong_tools": 1}
    report = run_validity(plain, lambda lib, q, a: float(len(a)), variants=["wrong_tools", "truncate_20"])
    assert report.summary()["n_noop"] == {"wrong_tools": 1}
    assert "no-op pairs  : 1 dropped" in report.format_summary()
    with pytest.raises(ValueError, match="unchanged"):
        run_validity(plain, lambda lib, q, a: 0.0, variants=["wrong_tools"])


def test_one_failing_variant_fails_the_gate():
    pairs = [{"base_id": f"b{i}", "variant": v, "question": "q", "library": "l",
              "intact": f"good{i}", "degraded": f"bad{i}{v}"} for i in range(4) for v in "abcde"]
    inverted = {p["degraded"] for p in pairs if p["variant"] == "e"}
    report = evaluate_pairs(lambda lib, q, a: 2.0 if a in inverted else (1.0 if a.startswith("good") else 0.0), pairs)
    assert report.summary()["accuracy"] == 0.8
    assert report.summary()["passed"] is False


def test_errored_pairs_count_against_the_gate():
    pairs = [{"base_id": f"b{i}", "variant": "v", "question": "q", "library": "l",
              "intact": f"good{i}", "degraded": f"bad{i}"} for i in range(10)]

    def flaky(lib, q, a):
        if a in {"good0", "good1", "good2"}:
            raise RuntimeError("throttled")
        return 1.0 if a.startswith("good") else 0.0

    s = evaluate_pairs(flaky, pairs).summary()
    assert (s["n_pairs"], s["n_errors"], s["accuracy"]) == (7, 3, 1.0)
    assert s["per_variant"]["v"]["gate_accuracy"] == 0.7
    assert s["passed"] is False
    assert "v                       7    3   1.00   0.70" in evaluate_pairs(flaky, pairs).format_summary()


def test_variant_whose_every_pair_errored_fails_the_gate():
    pairs = [{"base_id": "b", "variant": v, "question": "q", "library": "l",
              "intact": f"good{v}", "degraded": f"bad{v}"} for v in ("ok", "dead")]

    def scorer(lib, q, a):
        if a.endswith("dead"):
            raise RuntimeError("down")
        return 1.0 if a.startswith("good") else 0.0

    report = evaluate_pairs(scorer, pairs)
    assert report.summary()["passed"] is False
    assert report.summary()["per_variant"]["dead"]["n_errors"] == 1
    assert "dead                    0    1   0.00   0.00" in report.format_summary()


def test_report_is_written_before_a_console_that_cannot_print_it(tmp_path, monkeypatch):
    import io
    import json
    import sys

    import agent_benchmarks.eval.judge as judge_mod
    import agent_benchmarks.eval.judge_validity as jv
    from agent_benchmarks.cli import build_parser

    answers = tmp_path / "answers.json"
    answers.write_text(json.dumps(_answers()))
    out = tmp_path / "validity.json"
    monkeypatch.setattr(judge_mod, "Judge", lambda **kw: None)
    monkeypatch.setattr(jv, "judge_scorer", lambda judge: lambda lib, q, a: float(len(a)))
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(io.BytesIO(), encoding="cp1252"))
    args = build_parser().parse_args(["eval", "judge-validity", "--answers", str(answers),
                                      "--variants", "truncate_20", "--output", str(out)])
    with pytest.raises(UnicodeEncodeError):
        args.func(args)
    assert json.loads(out.read_text())["summary"]["n_pairs"] > 0


def test_mismatched_answer_is_drawn_per_base():
    answers = [
        {"question_id": f"Q{i}", "question_text": "q", "arms": {"a": {"answer": f"Answer {i}. " * 40}}}
        for i in range(6)
    ]
    pairs = build_pairs(answers, min_chars=100, variants=["mismatched_answer"])
    assert len(pairs) == 6
    assert len({p["degraded"] for p in pairs}) > 2
