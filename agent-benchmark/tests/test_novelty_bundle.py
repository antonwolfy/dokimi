# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""A skill is a bundle: what gets measured, what gets excluded, and where a span came from."""

from __future__ import annotations

import pytest

from agent_benchmarks.novelty.bundle import load_bundle, pointer_spans
from agent_benchmarks.novelty.spans import segment

SKILL = """\
---
name: accel-tuning
description: Configure the accelerator for training runs
---

# Accelerator tuning

Enable the accelerator with `--accel`. Do not enable it on driver 1.0.

Read `references/tuning.md` for the per-model table.

See `scripts/check.sh` before you start.

Use `patterns/warmup.md` with `--accel` on driver 2.1.
"""


@pytest.fixture
def skill(tmp_path):
    root = tmp_path / "accel-tuning"
    (root / "references").mkdir(parents=True)
    (root / "scripts").mkdir()
    (root / "patterns").mkdir()
    (root / "SKILL.md").write_text(SKILL, encoding="utf-8")
    (root / "references" / "tuning.md").write_text(
        "# Tuning\n\nSet `--threads` to the core count. Never exceed 64 threads.\n",
        encoding="utf-8",
    )
    (root / "scripts" / "check.sh").write_text("#!/bin/sh\nnvidia-smi --query\n", encoding="utf-8")
    (root / "patterns" / "warmup.md").write_text("Warm up for 30 s.\n", encoding="utf-8")
    (root / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n not text")
    return root


def test_the_entry_point_alone_still_counts_what_it_did_not_read(skill):
    bundle = load_bundle(f"skill:{skill}")
    assert bundle.summary()["n_files"] == 1
    assert bundle.text.lstrip().startswith("# Accelerator tuning")
    # The resources are counted on disk even though none were read, so the run can say
    # what share of the artifact it ignored.
    assert bundle.resource_words_on_disk > 0
    assert 0.0 < bundle.outside_share() < 1.0
    reasons = {row["path"]: row["reason"] for row in bundle.excluded}
    assert reasons.pop("logo.png") == "not text"   # never decoded, in either mode
    assert set(reasons.values()) == {"resources not requested"}


def test_a_bundle_run_reads_the_resources_and_keeps_their_provenance(skill):
    bundle = load_bundle(f"skill:{skill}", include_resources=True)
    paths = [item.path for item in bundle.files]
    assert paths[0] == "SKILL.md"
    assert set(paths[1:]) == {"references/tuning.md", "patterns/warmup.md", "scripts/check.sh"}
    roles = bundle.summary()["roles"]
    assert roles == {"reference": 1, "pattern": 1, "script": 1}
    # A binary file is excluded as not text, never decoded.
    assert [row["reason"] for row in bundle.excluded if row["path"] == "logo.png"] == ["not text"]

    assert "Never exceed 64 threads" in bundle.text
    offset = bundle.text.index("Never exceed 64 threads")
    assert bundle.source_of(offset) == "references/tuning.md"
    assert bundle.source_of(0) == "SKILL.md"
    assert bundle.body.lstrip().startswith("# Accelerator tuning")


def test_a_script_stays_one_span_instead_of_being_read_as_prose(skill):
    bundle = load_bundle(f"skill:{skill}", include_resources=True)
    script = next(item for item in bundle.files if item.path == "scripts/check.sh")
    assert script.text.startswith("```bash")
    code = [s for s in segment(bundle.text) if s.kind == "code" and "nvidia-smi" in s.text]
    assert len(code) == 1


def test_the_code_fence_is_not_counted_as_bundled_words(skill):
    bundle = load_bundle(f"skill:{skill}", include_resources=True)
    summary = bundle.summary()
    # Every text resource fits the default budgets, so all of it was read: measured must
    # equal on disk, not exceed it by the fence lines added around the script.
    assert summary["resource_words_measured"] == summary["resource_words_on_disk"]


def test_a_role_filter_and_the_word_budgets_record_every_exclusion(skill):
    only_refs = load_bundle(f"skill:{skill}", include_resources=True, roles=("reference",))
    assert [item.path for item in only_refs.files[1:]] == ["references/tuning.md"]
    filtered = {row["path"]: row["reason"] for row in only_refs.excluded}
    assert filtered["scripts/check.sh"] == "role filtered"

    tiny = load_bundle(f"skill:{skill}", include_resources=True, max_file_words=2)
    assert [item.path for item in tiny.files] == ["SKILL.md"]
    assert all("over max_file_words=2" in row["reason"] or row["reason"] == "not text"
               for row in tiny.excluded)

    capped = load_bundle(f"skill:{skill}", include_resources=True, max_total_words=5)
    # Reference files come first in role order, so the budget is spent there.
    assert [item.path for item in capped.files[1:]] == ["patterns/warmup.md"]
    assert any("over max_total_words=5" in row["reason"] for row in capped.excluded)


def test_a_span_that_only_names_a_bundled_file_is_a_pointer_not_waste(skill):
    bundle = load_bundle(f"skill:{skill}", include_resources=True)
    spans = segment(bundle.text)
    ids = pointer_spans(spans, bundle)
    by_id = {s.id: s.text for s in spans}
    # The per-file headings this module injects are scaffolding, reported as pointers so
    # they are not charged to the author as dead tokens. The author's own spans are what
    # the rest of this test is about.
    headers = {i for i in ids if by_id[i].startswith("## ")}
    assert headers and all(": " in by_id[i] for i in headers)
    pointing = {by_id[i] for i in ids - headers}

    assert any("references/tuning.md" in text for text in pointing)
    assert any("scripts/check.sh" in text for text in pointing)
    # Carries a flag and a version as well as a path, so it is knowledge, not a pointer.
    assert not any("patterns/warmup.md" in text for text in pointing)
    # Spans inside the resources themselves are never pointers.
    assert all(by_id[i] in SKILL for i in ids - headers)


def test_a_bare_directory_word_is_not_a_pointer(tmp_path):
    root = tmp_path / "perf"
    (root / "patterns").mkdir(parents=True)
    (root / "SKILL.md").write_text(
        "---\nname: perf\ndescription: d\n---\n\n"
        "# Performance patterns skill\n\nCount cache-references with perf stat.\n",
        encoding="utf-8",
    )
    (root / "patterns" / "cold.md").write_text("Annotate the cold path.\n", encoding="utf-8")
    bundle = load_bundle(f"skill:{root}", include_resources=True)
    spans = segment(bundle.text)
    authored = {s.id for s in spans if not s.text.startswith("## pattern: ")}
    assert pointer_spans(spans, bundle) & authored == set()


def test_a_text_artifact_has_no_bundle_to_read(tmp_path):
    path = tmp_path / "notes.md"
    path.write_text("# Notes\n\nAlways pin the driver.\n", encoding="utf-8")
    bundle = load_bundle(f"text:{path}", include_resources=True)
    assert [item.path for item in bundle.files] == ["notes.md"]
    assert (bundle.resource_words_on_disk, bundle.outside_share()) == (0, 0.0)
    assert pointer_spans(segment(bundle.text), bundle) == set()


def test_a_skill_s_own_evals_are_not_measured_as_its_content(tmp_path):
    root = tmp_path / "s"
    (root / "evals").mkdir(parents=True)
    (root / "references").mkdir()
    (root / "SKILL.md").write_text("---\nname: s\ndescription: d\n---\n\n# S\n",
                                   encoding="utf-8")
    (root / "evals" / "cases.json").write_text('{"question": "q", "answer": "a"}\n',
                                               encoding="utf-8")
    (root / "references" / "r.md").write_text("Pin the driver.\n", encoding="utf-8")

    default = load_bundle(f"skill:{root}", include_resources=True)
    # Probing atoms extracted from the skill's own answer key would credit it with
    # delivering its test set.
    assert [item.path for item in default.files[1:]] == ["references/r.md"]
    reason = {row["path"]: row["reason"] for row in default.excluded}["evals/cases.json"]
    assert "--resource-roles eval" in reason

    opted_in = load_bundle(f"skill:{root}", include_resources=True,
                           roles=("reference", "eval"))
    assert "evals/cases.json" in [item.path for item in opted_in.files]


def test_tool_and_vcs_directories_are_not_artifact_content(tmp_path):
    root = tmp_path / "s"
    (root / ".git").mkdir(parents=True)
    (root / "__pycache__").mkdir()
    (root / "references").mkdir()
    (root / "SKILL.md").write_text("---\nname: s\ndescription: d\n---\n\n# S\n",
                                   encoding="utf-8")
    (root / ".git" / "COMMIT_EDITMSG").write_text("wip\n", encoding="utf-8")
    (root / "__pycache__" / "x.py").write_text("cached = True\n", encoding="utf-8")
    (root / "references" / "r.md").write_text("one two three\n", encoding="utf-8")

    bundle = load_bundle(f"skill:{root}", include_resources=True)
    paths = {item.path for item in bundle.files} | {row["path"] for row in bundle.excluded}
    assert not any(p.startswith((".git/", "__pycache__/")) for p in paths)
    # They are not counted as unmeasured words either, or outside_share would be inflated.
    assert bundle.resource_words_on_disk == 3


def test_venv_and_hidden_files_are_not_measured(tmp_path):
    root = tmp_path / "s"
    for d in ("venv/lib", "env/bin", "references"):
        (root / d).mkdir(parents=True)
    (root / "SKILL.md").write_text("---\nname: s\ndescription: d\n---\n\n# S\n",
                                   encoding="utf-8")
    (root / "venv" / "lib" / "x.py").write_text("import os\n", encoding="utf-8")
    (root / "env" / "bin" / "activate").write_text("export PATH\n", encoding="utf-8")
    (root / ".notes.md").write_text("private scratch notes\n", encoding="utf-8")
    (root / "references" / ".draft.md").write_text("half done\n", encoding="utf-8")
    (root / "references" / "r.md").write_text("one two three\n", encoding="utf-8")

    bundle = load_bundle(f"skill:{root}", include_resources=True)
    paths = {item.path for item in bundle.files} | {row["path"] for row in bundle.excluded}
    assert paths == {"SKILL.md", "references/r.md"}
    assert bundle.resource_words_on_disk == 3


def test_a_bundled_image_does_not_make_the_run_warn_about_exclusions(tmp_path):
    root = tmp_path / "s"
    root.mkdir()
    (root / "SKILL.md").write_text("---\nname: s\ndescription: d\n---\n\n# S\n",
                                   encoding="utf-8")
    (root / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    bundle = load_bundle(f"skill:{root}", include_resources=True)
    assert [row["reason"] for row in bundle.excluded] == ["not text"]
    assert bundle.excluded_content() == []


def test_each_measured_file_records_a_digest_of_what_was_read(skill):
    bundle = load_bundle(f"skill:{skill}", include_resources=True)
    digests = {item.path: item.sha256 for item in bundle.files}
    assert all(value and value.startswith("sha256:") for value in digests.values())

    # A content edit that keeps the word count is exactly what a word count cannot see.
    reference = skill / "references" / "tuning.md"
    reference.write_text(reference.read_text(encoding="utf-8").replace("core", "CORE"),
                         encoding="utf-8")
    again = load_bundle(f"skill:{skill}", include_resources=True)
    changed = {item.path: item.sha256 for item in again.files}
    assert changed["references/tuning.md"] != digests["references/tuning.md"]
    assert changed["SKILL.md"] == digests["SKILL.md"]
    assert next(item for item in again.files
                if item.path == "references/tuning.md").words == next(
                    item for item in bundle.files
                    if item.path == "references/tuning.md").words


def test_a_second_file_named_skill_md_is_measured_like_any_other(tmp_path):
    root = tmp_path / "s"
    (root / "examples").mkdir(parents=True)
    (root / "SKILL.md").write_text("---\nname: s\ndescription: d\n---\n\n# S\n\none two\n",
                                   encoding="utf-8")
    (root / "examples" / "SKILL.md").write_text("A worked example with five words here\n",
                                                encoding="utf-8")
    bundle = load_bundle(f"skill:{root}", include_resources=True)
    # Skipping it by *name* hid it from the files, from `excluded` and from the on-disk
    # total, so `outside_share` under-reported what the run had not read.
    assert "examples/SKILL.md" in [item.path for item in bundle.files]
    assert bundle.resource_words_on_disk == 7


def test_an_unbalanced_code_fence_cannot_swallow_the_next_file(tmp_path):
    root = tmp_path / "s"
    (root / "references").mkdir(parents=True)
    (root / "SKILL.md").write_text("---\nname: s\ndescription: d\n---\n\n# S\n",
                                   encoding="utf-8")
    (root / "references" / "a-open.md").write_text("Quoting a fence:\n\n```\n",
                                                   encoding="utf-8")
    (root / "references" / "b-after.md").write_text("Never exceed 64 threads.\n",
                                                    encoding="utf-8")
    bundle = load_bundle(f"skill:{root}", include_resources=True)
    offset = bundle.text.index("Never exceed 64 threads")
    assert bundle.source_of(offset) == "references/b-after.md"
    spans = segment(bundle.text)
    carrier = next(s for s in spans if "Never exceed 64 threads" in s.text)
    # Without balancing, the open fence made one code span that reached into this file and
    # every later one, so their knowledge was attributed to the wrong source.
    assert carrier.kind != "code"
    assert bundle.source_of(carrier.start) == "references/b-after.md"


def _symlink(link, target, **kwargs):
    try:
        link.symlink_to(target, **kwargs)
    except OSError as exc:  # Windows without the symlink privilege (WinError 1314)
        pytest.skip(f"cannot create a symlink here: {exc}")


def test_a_symlink_is_recorded_rather_than_followed(tmp_path):
    outside = tmp_path / "outside.md"
    outside.write_text("Secret note from outside the skill.\n", encoding="utf-8")
    root = tmp_path / "s"
    (root / "references").mkdir(parents=True)
    (root / "SKILL.md").write_text("---\nname: s\ndescription: d\n---\n\n# S\n",
                                   encoding="utf-8")
    _symlink(root / "references" / "link.md", outside)
    bundle = load_bundle(f"skill:{root}", include_resources=True)
    assert "Secret note" not in bundle.text
    assert {row["path"]: row["reason"] for row in bundle.excluded} == {
        "references/link.md": "symlink"}


def test_a_directory_or_dangling_symlink_is_recorded_too(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "note.md").write_text("Words from outside the skill.\n", encoding="utf-8")
    root = tmp_path / "s"
    (root / "references").mkdir(parents=True)
    (root / "SKILL.md").write_text("---\nname: s\ndescription: d\n---\n\n# S\n",
                                   encoding="utf-8")
    _symlink(root / "references" / "linked", outside, target_is_directory=True)
    _symlink(root / "references" / "gone.md", tmp_path / "missing.md")
    bundle = load_bundle(f"skill:{root}", include_resources=True)
    assert "outside the skill" not in bundle.text
    assert {row["path"]: row["reason"] for row in bundle.excluded} == {
        "references/linked": "symlink", "references/gone.md": "symlink"}


def test_a_pointer_span_that_pins_a_value_or_a_rule_is_knowledge(tmp_path):
    root = tmp_path / "s"
    (root / "scripts").mkdir(parents=True)
    (root / "SKILL.md").write_text(
        "---\nname: s\ndescription: d\n---\n\n# S\n\n"
        "See `scripts/bench.sh` before you start.\n\n"
        "Run `scripts/bench.sh` with 8 threads.\n\n"
        "Run `scripts/bench.sh` -j8 for the sweep.\n\n"
        "`scripts/bench.sh` must be run before the measurement, never after.\n",
        encoding="utf-8")
    (root / "scripts" / "bench.sh").write_text("#!/bin/sh\ntrue\n", encoding="utf-8")
    bundle = load_bundle(f"skill:{root}", include_resources=True)
    spans = segment(bundle.text)
    pointing = {s.text for s in spans if s.id in pointer_spans(spans, bundle)}

    assert any("before you start" in text for text in pointing)   # loading instruction
    for carries_knowledge in ("with 8 threads", "-j8", "never after"):
        assert not any(carries_knowledge in text for text in pointing), carries_knowledge


def test_policy_exclusions_are_not_charged_as_unread_content(tmp_path):
    root = tmp_path / "s"
    (root / "evals").mkdir(parents=True)
    (root / "references").mkdir()
    (root / "SKILL.md").write_text("---\nname: s\ndescription: d\n---\n\n# S\n",
                                   encoding="utf-8")
    (root / "evals" / "cases.md").write_text("one two three four five\n", encoding="utf-8")
    (root / "references" / "r.md").write_text("six seven\n", encoding="utf-8")
    summary = load_bundle(f"skill:{root}", include_resources=True).summary()
    assert summary["resource_words_measured"] == 2
    assert summary["resource_words_on_disk"] == 7
    # The eval file can never be measured, so it is a decision, not a gap.
    assert summary["policy_excluded_words"] == 5
    assert summary["unmeasured_words"] == 0


def test_text_is_decided_by_content_not_by_suffix(tmp_path):
    root = tmp_path / "s"
    for d in ("references", "scripts", "assets"):
        (root / d).mkdir(parents=True)
    (root / "SKILL.md").write_text("---\nname: s\ndescription: d\n---\n\n# S\n",
                                   encoding="utf-8")
    # Real bundles ship extension-less guides and scripts, `.mjs`, `Makefile`, `.xml`...
    (root / "references" / "guide").write_text("# Guide\n\nNever exceed 64 threads.\n",
                                                encoding="utf-8")
    (root / "scripts" / "tool.mjs").write_text("export const threads = 64;\n",
                                               encoding="utf-8")
    (root / "scripts" / "Makefile").write_text("all:\n\tmake it\n", encoding="utf-8")
    (root / "assets" / "blob").write_bytes(b"BM\x00\x00\x00\x00 binary with NUL bytes")
    (root / "assets" / "latin1.txt").write_bytes(b"caf\xe9 au lait\n")

    bundle = load_bundle(f"skill:{root}", include_resources=True)
    measured = {item.path: item for item in bundle.files[1:]}
    assert set(measured) == {"references/guide", "scripts/tool.mjs", "scripts/Makefile"}
    # Unknown suffixes are fenced so the segmenter keeps them whole.
    assert measured["scripts/tool.mjs"].text.startswith("```")
    assert bundle.resource_words_on_disk == 6 + 5 + 3
    assert bundle.excluded_content() == []
    # A binary is not text; a prose file that does not decode is text this run did not
    # read, so it is counted for the coverage gate instead of vanishing.
    assert {row["path"]: row["reason"] for row in bundle.excluded} == {
        "assets/blob": "not text", "assets/latin1.txt": "unreadable"}
    assert bundle.unreadable_files == 1


def test_a_utf8_bom_does_not_change_a_file_s_digest_or_its_text(tmp_path):
    root = tmp_path / "s"
    (root / "references").mkdir(parents=True)
    (root / "SKILL.md").write_text("---\nname: s\ndescription: d\n---\n\n# S\n",
                                   encoding="utf-8")
    (root / "references" / "bom.md").write_bytes(b"\xef\xbb\xbf# Install\n\none two\n")
    (root / "references" / "plain.md").write_bytes(b"# Install\n\none two\n")
    bundle = load_bundle(f"skill:{root}", include_resources=True)
    digests = {item.path: item.sha256 for item in bundle.files[1:]}
    # Saving a reference as "UTF-8 with BOM" is an editor artifact, like a line-ending
    # change: it is not an edit, and the entry point already has its BOM stripped.
    assert digests["references/bom.md"] == digests["references/plain.md"]
    assert "\ufeff" not in bundle.text
    assert {s.kind for s in segment(bundle.text) if s.text.endswith("# Install")} == {"heading"}


@pytest.mark.parametrize("quoted", [
    "Example:\n\n```\ncode\n~~~\n",                      # ``` never closed by ~~~
    "Use tildes when quoting backticks:\n\n~~~\n```\n~~~\n",  # closed; parity would reopen
    "Quoting:\n\n~~~\n",                                  # ~~~ open; ``` cannot close it
])
def test_fence_balancing_follows_the_segmenter_s_same_marker_rule(tmp_path, quoted):
    root = tmp_path / "s"
    (root / "references").mkdir(parents=True)
    (root / "SKILL.md").write_text("---\nname: s\ndescription: d\n---\n\n# S\n",
                                   encoding="utf-8")
    (root / "references" / "a-open.md").write_text(quoted, encoding="utf-8")
    (root / "references" / "b-after.md").write_text("Never exceed 64 threads.\n",
                                                    encoding="utf-8")
    bundle = load_bundle(f"skill:{root}", include_resources=True)
    spans = segment(bundle.text)
    carrier = next(s for s in spans if "Never exceed 64 threads" in s.text)
    # The segmenter closes a fence only on the marker that opened it. Counting fence lines
    # mod 2 with ``` and ~~~ interchangeable disagreed with it three ways, and each one
    # swallowed the next file into a code span attributed to this one.
    assert carrier.kind != "code"
    assert bundle.source_of(carrier.start) == "references/b-after.md"


def test_policy_accounting_does_not_depend_on_the_mode_or_the_flag(tmp_path):
    root = tmp_path / "s"
    (root / "evals").mkdir(parents=True)
    (root / "references").mkdir()
    (root / "SKILL.md").write_text("---\nname: s\ndescription: d\n---\n\n# S one two\n",
                                   encoding="utf-8")
    (root / "evals" / "cases.md").write_text("one two three four five\n", encoding="utf-8")
    (root / "references" / "r.md").write_text("six seven\n", encoding="utf-8")
    (root / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    entry_only = load_bundle(f"skill:{root}")
    included = load_bundle(f"skill:{root}", include_resources=True)
    # The eval file is a decision in both modes: the entry-point run must not promise
    # that --include-resources will measure it, and the same bytes must give the same
    # policy/gap split whichever flag produced the summary.
    for bundle in (entry_only, included):
        assert bundle.policy_excluded_words() == 5
        assert bundle.outside_share() == round(7 / 11, 4)          # on disk, as documented
        assert bundle.measurable_outside_share() == round(2 / 6, 4)
    assert entry_only.unmeasured_words() == 2
    assert [row["path"] for row in entry_only.excluded_content()] == ["references/r.md"]
    assert included.unmeasured_words() == 0
    assert included.excluded_content() == []
    assert {row["path"]: row["kind"] for row in included.excluded} == {
        "evals/cases.md": "policy", "logo.png": "not_text"}

    # An explicit --resource-roles is the user's decision, not a gap either.
    filtered = load_bundle(f"skill:{root}", include_resources=True, roles=("eval",))
    assert filtered.policy_excluded_words() == 2
    assert filtered.unmeasured_words() == 0


def test_a_bundle_that_is_only_evals_has_nothing_measurable_outside_its_entry_point(tmp_path):
    root = tmp_path / "s"
    (root / "evals").mkdir(parents=True)
    (root / "SKILL.md").write_text("---\nname: s\ndescription: d\n---\n\n# S\n",
                                   encoding="utf-8")
    (root / "evals" / "cases.json").write_text(" ".join(["q"] * 50), encoding="utf-8")
    bundle = load_bundle(f"skill:{root}")
    assert bundle.outside_share() > 0.9
    assert bundle.measurable_outside_share() == 0.0
    assert bundle.unmeasured_words() == 0
    assert bundle.excluded_content() == []


@pytest.mark.parametrize("name, raw", [
    ("references/u.md", "# Guide\nNever exceed 64 threads.\n".encode("utf-16")),
    ("references/guide", "caf\xe9 Never exceed 64 threads.\n".encode("latin-1")),
    ("scripts/x.py", "# caf\xe9\nx = 1\n".encode("latin-1")),
])
def test_text_in_another_encoding_is_unreadable_not_silently_dropped(tmp_path, name, raw):
    """A UTF-16 .md, a latin-1 script or an extension-less guide is content the run did not read."""
    root = tmp_path / "s"
    (root / "references").mkdir(parents=True)
    (root / "scripts").mkdir()
    (root / "SKILL.md").write_text("---\nname: s\ndescription: d\n---\n\n# S\n", encoding="utf-8")
    (root / name).write_bytes(raw)
    bundle = load_bundle(f"skill:{root}", include_resources=True)
    assert bundle.unreadable_files == 1
    assert [row["kind"] for row in bundle.excluded] == ["unreadable"]


def test_a_blob_without_nul_bytes_is_still_not_text(tmp_path):
    root = tmp_path / "s"
    (root / "assets").mkdir(parents=True)
    (root / "SKILL.md").write_text("---\nname: s\ndescription: d\n---\n\n# S\n", encoding="utf-8")
    (root / "assets" / "logo").write_bytes(bytes(range(128, 256)) * 20)
    bundle = load_bundle(f"skill:{root}", include_resources=True)
    assert bundle.unreadable_files == 0
    assert bundle.excluded[0]["kind"] == "not_text"
