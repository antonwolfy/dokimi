# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Edge cases of the L1 reach probe found in review (no LLM; the fake harness of test_repo_reach)."""

from __future__ import annotations

import pytest
from test_repo_reach import _reach, _write

from dokimi.repos import SourceError, WorkTree
from dokimi.repos.events import OUTPUT_KEEP, clip_output
from dokimi.repos.reach import ReachError, distinct_salt, prose_words, resolve_links, scenarios, token


def test_a_directory_named_root_gets_its_own_scenario():
    ids = [s.id for s in scenarios(["CLAUDE.md", "root/CLAUDE.md"], ("root", "cwd"))]
    assert ids == ["cwd=.", "cwd=root"]
    assert len(set(ids)) == len(ids)


def test_prose_counts_words_not_formatting():
    assert prose_words("`RC111111`\n`RC222222`\n`RC333333`\n`RC444444`\n`RC555555`") == 0
    assert prose_words("1. RC111111\n2. RC222222\n3) RC333333\n```\nRC444444\n```") == 0
    assert prose_words("NONE") == 0
    assert prose_words("I will not list these tokens.") == 5


def test_unreadable_guidance_is_a_reach_error(tmp_path, monkeypatch):
    original = WorkTree.read_text

    def broken(self, path):
        if path == "sub/AGENTS.md":
            raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")
        return original(self, path)

    monkeypatch.setattr(WorkTree, "read_text", broken)
    with pytest.raises(ReachError, match="cannot read guidance file sub/AGENTS.md"):
        _reach(tmp_path, monkeypatch, kinds=("root",))


def test_old_traces_are_removed(tmp_path, monkeypatch):
    stale = tmp_path / "out" / "traces" / "07-cwd_gone.stdout"
    _write(tmp_path, "out/traces/07-cwd_gone.stdout", "from an earlier run\n")
    _write(tmp_path, "out/traces/notes.txt", "not ours\n")
    _write(tmp_path, "out/traces/104-read_gone.events.jsonl", "{}\n")  # {n:02d} widens past 99 scenarios
    _reach(tmp_path, monkeypatch, kinds=("root",))
    names = sorted(p.name for p in (tmp_path / "out" / "traces").iterdir())
    assert not stale.exists() and "104-read_gone.events.jsonl" not in names
    assert "notes.txt" in names and any(n.startswith("00-") for n in names)


def test_salt_is_changed_until_every_token_is_distinct(monkeypatch):
    tree = type("T", (), {"read_text": lambda self, p: "mentions RCAAAAAA already\n"})()
    real = token

    def colliding(salt, path, position):
        if salt == "s":  # first salt: two files share a token
            return "RCBBBBBB" if position == "head" else real(salt, path, position)
        if salt == "s-1":  # second: a token the guidance already contains
            return "RCAAAAAA" if (path, position) == ("a.md", "tail") else real(salt, path, position)
        return real(salt, path, position)

    monkeypatch.setattr("dokimi.repos.reach.token", colliding)
    assert distinct_salt(tree, ["a.md", "b.md"], "s") == "s-2"


def test_clip_counts_the_bytes_really_omitted():
    text = "a" + "é" * 6000  # 2 bytes each, after one 1-byte character: the head cut splits an é
    clipped, truncated = clip_output(text)
    head, rest = clipped.split("\n[... ", 1)
    omitted = int(rest.split(" bytes omitted", 1)[0])
    tail = rest.split("...]\n", 1)[1]
    assert truncated and len(head.encode()) == OUTPUT_KEEP - 1
    assert omitted == len(text.encode()) - len(head.encode()) - len(tail.encode())


def test_a_harness_that_drops_tokens_gives_truncated_cells(tmp_path, monkeypatch):
    payload = _reach(tmp_path, monkeypatch, mode="truncate", kinds=("root",))
    classes = {r["file"]: r["class"] for r in payload["records"]}
    assert classes["CLAUDE.md"] == "truncated"  # the fake reports every other token


def test_a_link_into_git_or_to_nothing_is_not_probed(tmp_path, monkeypatch):
    tree = type("T", (), {"resolve": lambda self, path: ".git/config" if path == "a.md" else path})()
    assert resolve_links(tree, ["a.md", "b.md"]) == (
        {"b.md": []}, [{"path": "a.md", "reason": "a.md links to an unsafe path: .git/config"}])

    def dangling(self, path):
        raise SourceError(f"{path} links to nothing: gone.md")

    monkeypatch.setattr(WorkTree, "resolve", dangling)
    with pytest.raises(ReachError, match="each is a link that cannot be followed: .* links to nothing"):
        _reach(tmp_path, monkeypatch, kinds=("root",))
