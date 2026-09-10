"""Tests for scripts/check_treatment_batch.py — the acceptance gate for an arms.v1 batch.

The gate exists because the batch it replaced was accepted by eye and turned out to be
unusable. So the thing worth testing is not that a good batch passes: it is that each gate
*fires*, because a gate that quietly holds by construction reads exactly like a green one.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_treatment_batch.py"
_spec = importlib.util.spec_from_file_location("check_treatment_batch", _SCRIPT)
assert _spec and _spec.loader
ctb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ctb)

ARM = "profile:concise_expert"
DIGEST = "sha256:" + "a" * 64


def _cell(n=2, arm=ARM, *, scored=None, generated=None, sent=None, digest=DIGEST):
    """One passing arms.v1 cell, with knobs for each thing the gate is supposed to catch."""
    scored = n if scored is None else scored
    generated = n if generated is None else generated
    sent = generated if sent is None else sent
    return {
        "schema_version": "arms.v1",
        "arms": ["baseline", arm],
        "baseline_arm": "baseline",
        "model": "answering-model",
        "judge_model": ctb.JUDGE_MODEL,
        "judge_provider": ctb.JUDGE_PROVIDER,
        "total_questions": n,
        "evaluations": [
            {
                "question_id": f"Q{i}",
                "scores": {
                    "baseline": {"aggregate": 5.0},
                    arm: {"aggregate": 7.0} if i < scored else {"aggregate": None},
                },
            }
            for i in range(n)
        ],
        "answers": [
            {
                "question_id": f"Q{i}",
                "arms": {
                    "baseline": {"answer": "b"},
                    arm: {
                        "answer": "t" if i < generated else "",
                        "used_system_prompt": i < sent,
                        "metadata": {"profile_prompt_sha256": digest},
                    },
                },
            }
            for i in range(n)
        ],
    }


def _write(tmp_path, name, artifact):
    path = tmp_path / name
    path.write_text(json.dumps(artifact), encoding="utf-8")
    return path


def _problems(tmp_path, name, artifact, **kw):
    kw.setdefault("treatment_pattern", "profile:*")
    kw.setdefault("judge_model", ctb.JUDGE_MODEL)
    kw.setdefault("sizes", {"regular": 2})
    return ctb.check_file(_write(tmp_path, name, artifact), **kw)["problems"]


def test_a_clean_cell_passes(tmp_path):
    assert _problems(tmp_path, "m_regular.json", _cell()) == []


# --- the count gate must not be able to hold by construction ----------------


def test_a_filename_outside_the_suffix_map_is_reported_not_silently_trusted(tmp_path):
    """`total_questions` is written as len(records), so falling back to it gates nothing.

    A cell short by half still self-reports its own length, and every count check then
    compares that length against itself. The fallback has to announce itself.
    """
    short = _cell(n=1)
    problems = _problems(tmp_path, "m_unlabelled.json", short)
    assert any("matches none of the --expect-n suffixes" in p for p in problems)


def test_the_fallback_is_silent_when_the_count_gate_was_explicitly_disabled(tmp_path):
    """`--expect-n ''` is a deliberate opt-out and must not nag."""
    problems = _problems(tmp_path, "m_unlabelled.json", _cell(), sizes={})
    assert not any("--expect-n" in p for p in problems)


def test_a_short_run_fails_when_the_suffix_is_present(tmp_path):
    problems = _problems(tmp_path, "m_regular.json", _cell(n=1), sizes={"regular": 2})
    assert any("1 evaluations, want 2" in p for p in problems)


def test_a_suffix_map_that_does_not_describe_the_question_set_is_flagged(tmp_path):
    """golden sets run 20, 24 or 111 questions by product; the suffix cannot know which.

    Trusting the map alone turns a mis-specified batch into a row of confident counts, so
    the gate cross-checks it against what the artifact says it ran.
    """
    artifact = _cell(n=2)
    artifact["total_questions"] = 111
    problems = _problems(tmp_path, "m_golden.json", artifact, sizes={"golden": 2})
    assert any("total_questions=111 but --expect-n wants 2" in p for p in problems)


def test_an_unjudged_cell_fails_even_with_no_count_gate(tmp_path):
    """`if evaluations:` skipped the coverage gate entirely for an empty cell."""
    empty = _cell(n=0)
    empty.pop("total_questions")
    problems = _problems(tmp_path, "m_unlabelled.json", empty, sizes={})
    assert any("0 evaluations" in p for p in problems)


def test_partial_judge_coverage_fails(tmp_path):
    problems = _problems(
        tmp_path, "m_regular.json", _cell(n=4, scored=2), sizes={"regular": 4}
    )
    assert any("scored in both arms" in p for p in problems)


# --- persona routing --------------------------------------------------------


def test_a_persona_arm_that_generated_nothing_does_not_pass_the_routing_gate(tmp_path):
    """The `present > 0` guard keeps a proxy outage from reading as a routing bug — but on
    its own it also let a cell with no generated answer pass the routing gate in silence."""
    problems = _problems(
        tmp_path, "m_regular.json", _cell(n=2, generated=0), sizes={"regular": 2}
    )
    assert any("generated 0 answers" in p for p in problems)
    assert not any("MISROUTED" in p for p in problems)


def test_a_persona_that_did_not_reach_the_model_is_a_code_bug(tmp_path):
    problems = _problems(
        tmp_path, "m_regular.json", _cell(n=2, sent=1), sizes={"regular": 2}
    )
    assert any("MISROUTED PERSONA" in p for p in problems)


def test_a_baseline_carrying_a_system_prompt_fails(tmp_path):
    artifact = _cell()
    artifact["answers"][0]["arms"]["baseline"]["used_system_prompt"] = True
    problems = _problems(tmp_path, "m_regular.json", artifact)
    assert any("baseline sent a system prompt" in p for p in problems)


# --- provenance -------------------------------------------------------------


def test_a_stale_prompt_digest_fails(tmp_path):
    """The arm is named after the profile's frontmatter id, so an in-place edit leaves old
    cells with the same arm name; only the digest separates them."""
    problems = _problems(
        tmp_path, "m_regular.json", _cell(), want_digest="sha256:" + "b" * 64
    )
    assert any("STALE ARTIFACT" in p for p in problems)


def test_an_unstamped_cell_cannot_prove_which_prompt_it_scored(tmp_path):
    artifact = _cell(digest=None)
    for answer in artifact["answers"]:
        answer["arms"][ARM]["metadata"] = {}
    problems = _problems(tmp_path, "m_regular.json", artifact, want_digest=DIGEST)
    assert any("no profile_prompt_sha256" in p for p in problems)


def test_self_judging_fails(tmp_path):
    artifact = _cell()
    artifact["model"] = ctb.JUDGE_MODEL
    problems = _problems(tmp_path, "m_regular.json", artifact)
    assert any("SELF-JUDGING" in p for p in problems)


def test_a_third_arm_breaks_parity_with_the_docs_and_skills_batches(tmp_path):
    artifact = _cell()
    artifact["arms"] = ["baseline", ARM, "docs"]
    problems = _problems(tmp_path, "m_regular.json", artifact)
    assert any("want exactly 2" in p for p in problems)


def test_a_treatment_arm_of_the_wrong_kind_fails(tmp_path):
    problems = _problems(
        tmp_path, "m_regular.json", _cell(arm="skill:demo-skill"),
    )
    assert any("does not match" in p for p in problems)


# --- flag parsing -----------------------------------------------------------


@pytest.mark.parametrize(
    "spec,want",
    [
        ("regular=40,golden=20", {"regular": 40, "golden": 20}),
        ("40", {"": 40}),
        ("", {}),
        ("  golden=24  ", {"golden": 24}),
    ],
)
def test_parse_expect_n(spec, want):
    assert ctb.parse_expect_n(spec) == want


@pytest.mark.parametrize("spec", ["regular", "regular=x", "regular=40,golden"])
def test_parse_expect_n_rejects_junk(spec):
    with pytest.raises(Exception, match="expect-n"):
        ctb.parse_expect_n(spec)
