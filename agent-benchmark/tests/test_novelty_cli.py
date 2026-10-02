# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""CLI wiring for `novelty`: parsing, role defaults, and the guards that refuse a run."""

from __future__ import annotations

import json

import pytest

from agent_benchmarks.cli import build_parser
from agent_benchmarks.commands import novelty as novelty_cmd


def _parse(*argv):
    return build_parser().parse_args(list(argv))


def test_every_subcommand_is_registered():
    for sub in ("analyze", "atoms", "probe", "shorten", "view"):
        args = _parse("novelty", sub, *(
            ["--artifact", "skill:x"] if sub != "view" else ["--novelty", "n.json"]
        ), *(["--atoms", "a.json"] if sub in ("probe", "shorten", "view") else []))
        assert args.novelty_cmd == sub
        assert callable(args.func)


def test_the_judge_defaults_to_a_different_model_than_the_answerer():
    args = _parse("novelty", "analyze", "--artifact", "skill:x", "--model", "gpt-4o-mini")
    extractor, answerer, judge = novelty_cmd._clients(args)
    assert judge.model != answerer.model
    assert extractor.role == "extractor" and judge.role == "judge"


def test_the_extractor_follows_the_judge_not_the_answerer():
    """The model being measured must not write its own answer key."""
    args = _parse(
        "novelty", "analyze", "--artifact", "skill:x",
        "--model", "model-a", "--judge-model", "model-b",
    )
    extractor, answerer, _judge = novelty_cmd._clients(args)
    assert extractor.model == "model-b"
    assert answerer.model == "model-a"


def test_dropping_the_baseline_arm_is_refused():
    with pytest.raises(SystemExit, match="paired"):
        novelty_cmd._arms("full,placebo")
    assert novelty_cmd._arms("no_artifact,full,shuffled") == ["no_artifact", "full", "shuffled"]


def test_a_missing_artifact_exits_with_a_message(capsys):
    args = _parse("novelty", "analyze", "--artifact", "text:/nonexistent/skill.md")
    with pytest.raises(SystemExit, match="cannot load"):
        args.func(args)
    capsys.readouterr()


def test_max_atoms_rejects_zero():
    with pytest.raises(SystemExit):
        _parse("novelty", "analyze", "--artifact", "skill:x", "--max-atoms", "0")


def test_atoms_subcommand_writes_atoms_and_span_stats(tmp_path, monkeypatch, capsys):
    skill = tmp_path / "s" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        "---\nname: s\ndescription: d\n---\n\n# H\n\nDo not enable the legacy driver.\n",
        encoding="utf-8",
    )
    rows = [{
        "statement": "The legacy driver must not be enabled.",
        "question": "Should the legacy driver be enabled?",
        "answer": "No.", "kind": "contract", "tags": ["negative_constraint"],
        "span_ids": ["s0002"],
    }]

    def transport(prompt, system=None):
        if "Extract the checkable knowledge" in prompt:
            return json.dumps(rows), None
        return json.dumps({"verdict": "supported"}), None

    real_client = novelty_cmd._client
    monkeypatch.setattr(
        novelty_cmd, "_client",
        lambda model, provider, role, args: _with_transport(
            real_client(model, provider, role, args), transport
        ),
    )
    out = tmp_path / "atoms.json"
    args = _parse("novelty", "atoms", "--artifact", f"skill:{skill}", "--out", str(out))
    args.func(args)
    payload = json.loads(out.read_text())
    assert len(payload["atoms"]) == 1
    assert payload["atoms"][0]["faithfulness"] == "supported"
    assert any("negation" in span["protection"] for span in payload["spans"])
    assert "Saved 1 atoms" in capsys.readouterr().out
    assert (payload["extractor"], payload["cap"]) == ("gpt-4o-mini", 120)

    # With defaults the model under measurement wrote this answer key; probe says so.
    args = _parse("novelty", "probe", "--artifact", f"skill:{skill}", "--atoms", str(out),
                  "--no-paraphrase", "--no-reversal", "--out", str(tmp_path / "p.json"))
    args.func(args)
    assert "own answer key" in capsys.readouterr().err


def test_view_says_its_colours_come_from_spans_only(tmp_path, capsys):
    from agent_benchmarks.artifacts import save_artifact
    from agent_benchmarks.novelty.atoms import Atom, save_atoms
    from agent_benchmarks.novelty.spans import index_atoms, segment

    spans = segment("# H\n\nDo not enable the legacy driver.\n")
    atom = Atom(statement="No legacy driver.", question="q", answer="No.",
                span_ids=(spans[1].id,))
    index_atoms(spans, [atom])
    atoms_path = tmp_path / "atoms.json"
    save_atoms([atom], spans, atoms_path)

    novelty_path = tmp_path / "novelty.json"
    save_artifact("novelty", _minimal_artifact(), novelty_path)
    out = tmp_path / "annotated.md"
    args = _parse(
        "novelty", "view", "--novelty", str(novelty_path), "--atoms", str(atoms_path),
        "--format", "md", "--out", str(out),
    )
    args.func(args)
    assert "legacy driver" in out.read_text()
    assert "colours here come from spans" in capsys.readouterr().out


def _with_transport(client, transport):
    client.transport = transport
    return client


def _minimal_artifact() -> dict:
    empty = {
        "added": 0, "redundant": 0, "degraded": 0, "still_missing": 0,
        "n_paired": 0, "n_unpaired_dropped": 0, "ci95_added": None,
    }
    return {
        "generated_at": "2026-09-23T00:00:00Z",
        "artifact": {"kind": "skill", "ref": "skill:x", "ref_digest": None, "tokens": 10},
        "model": "model-a",
        "judge_model": "model-b",
        "atoms": {"n": 1, "n_probed": 0, "sampling": "full", "faithfulness": {}},
        "paired": {"lenient": dict(empty), "strict": dict(empty)},
        "k0": {"lenient": 0.0, "strict": 0.0},
        "spans": {"n": 2, "tokens": 10, "tokens_carrying_nothing": 4,
                  "frac_carrying_nothing": 0.4, "sole_carrier": 1, "protected": 1,
                  "by_kind": {"heading": 1, "sentence": 1}},
    }


def test_novelty_ref_digest_is_the_subject_scorecard_digest(tmp_path):
    # Both artifacts write `ref_digest`; a directory hashed two ways could never be matched.
    from agent_benchmarks.commands.novelty import _digest
    from agent_benchmarks.subjects.scorecard import _digest_ref

    (tmp_path / "references").mkdir()
    (tmp_path / "SKILL.md").write_text("---\nname: s\n---\nbody\n")
    (tmp_path / "references" / "a.md").write_text("ref\n")
    assert _digest(f"skill:{tmp_path}") == _digest_ref(str(tmp_path), base=tmp_path)
