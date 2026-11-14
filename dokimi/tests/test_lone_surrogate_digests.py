# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""A hash of text that holds a lone surrogate (a surrogate-escaped argv value or file name, a ``\\udXXX`` JSON escape) must not raise.

The digest of every input that encodes as UTF-8 stays what it was; two different surrogates stay apart.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="a surrogate-escaped name is a POSIX file-name form")


@posix_only
def test_cache_path_of_a_remote_url_with_a_non_utf8_byte_is_a_directory_name():
    from dokimi.repos.source import RepoSource, cache_path

    source = RepoSource.parse("https://example.com/n\udcff@" + "a" * 40)
    assert source.location == "https://example.com/n\udcff"
    assert cache_path(source.location, Path("/c")) == Path("/c/n_-4d0dae2da255.git")
    assert cache_path("https://example.com/n\udcfe", Path("/c")) == Path("/c/n_-e1417c254653.git")


def test_cache_path_of_a_utf8_url_is_unchanged():
    from dokimi.repos.source import cache_path

    assert cache_path("https://example.com/org/repo.git", Path("/c")) == Path("/c/repo-e9497c38e4fa.git")


@posix_only
def test_harness_id_with_a_non_utf8_byte_and_a_reserved_character_is_a_directory_name():
    from dokimi.harnesses.runner import _safe_id

    assert _safe_id("n\udcff?") == "n\udcff_-2d5da54d"
    assert _safe_id("n\udcfe?") == "n\udcfe_-f6a8699d"


def test_harness_id_with_a_reserved_character_keeps_its_directory_name():
    from dokimi.harnesses.runner import _safe_id

    assert _safe_id("a:b?c") == "a_b_c-f1b58422"
    assert _safe_id("plain") == "plain"


@posix_only
def test_reach_token_of_a_file_name_with_a_non_utf8_byte_is_a_token():
    from dokimi.repos.reach import token

    assert token("s", "n\udcff", "p") == "RCE80092"
    assert token("s", "n\udcfe", "p") == "RC18DC10"


def test_reach_token_of_a_utf8_path_is_unchanged():
    from dokimi.repos.reach import token

    assert token("s", "a/b.py", "p") == "RCC6EA29"


@posix_only
def test_skill_reach_token_of_a_case_id_with_a_non_utf8_byte_is_a_token():
    from dokimi.repos.skill_reach import token

    assert token("s", "n\udcff", "p") == "SBE80092"
    assert token("s", "n\udcfe", "p") == "SB18DC10"


def test_skill_reach_token_of_a_utf8_case_id_is_unchanged():
    from dokimi.repos.skill_reach import token

    assert token("s", "case-1", "p") == "SB7667F2"
    assert token("s", "case-1", "description") == "SKE40028"


@posix_only
def test_url_client_cache_key_of_a_source_with_a_non_utf8_byte_is_a_digest():
    from dokimi.mcp.url_client import URLClient

    assert URLClient("n\udcff")._cache_key() == "8a8f844082c0b6790a883eca6bd8260acd6b5ce42eca3e591fe7f9db764e6a57"
    assert URLClient("n\udcfe")._cache_key() == "fad35f9379fa9598c32b2a7fa48575cf213ef99b59955fef2f454bd4a2aff8e8"


def test_url_client_cache_key_of_a_utf8_url_is_unchanged():
    from dokimi.mcp.url_client import URLClient

    key = URLClient("https://example.com/doc")._cache_key()
    assert key == "9813a80c59ae8111adf2b881b481b0a6334db465cd7c961d98cec1830f9aa1db"  # gitleaks:allow: the sha256 of a test URL


def _graph_candidate(*symbols: str):
    from dokimi.repos.graph_tasks import Candidate

    return Candidate("references", symbols, "run", "run", (), (), (), 1)


@posix_only
def test_graph_task_id_of_a_symbol_with_a_non_utf8_byte_is_an_id():
    from dokimi.repos.graph_tasks import task_id

    assert task_id(_graph_candidate("n\udcff")) == "graph_references_run_8a8f8440"
    assert task_id(_graph_candidate("n\udcfe")) == "graph_references_run_fad35f93"


def test_graph_task_id_of_utf8_symbols_is_unchanged():
    from dokimi.repos.graph_tasks import task_id

    assert task_id(_graph_candidate("scip-python python pkg 1 mod/run().")) == "graph_references_run_89eac09d"
    assert task_id(_graph_candidate("a", "b")) == "graph_references_run_7e18f737"


def _delta_artifact_name(baseline_name: str) -> str:
    from dokimi.eval.matrix_rollup import _paired_plugin_deltas
    from tests.test_matrix_rollup import _arms_artifact

    cells = [(baseline_name, Path("a"), _arms_artifact(baseline_name)),
             ("p", Path("b"), _arms_artifact("p", "caveman:full"))]
    deltas, warnings = _paired_plugin_deltas(cells, Path("/out"))
    assert warnings == [] and len(deltas) == 1
    return Path(deltas[0]["artifact"]).name


def test_matrix_pair_suffix_of_a_cell_name_with_a_lone_surrogate_is_a_digest():
    assert _delta_artifact_name("n\udcff") == "plugin-delta-n-to-p-8598c7f9.json"
    assert _delta_artifact_name("n\udcfe") == "plugin-delta-n-to-p-ce83522b.json"
    assert _delta_artifact_name("n\ud800") == "plugin-delta-n-to-p-7e558003.json"
    assert _delta_artifact_name("n\udbff") == "plugin-delta-n-to-p-e4429709.json"


def test_matrix_pair_suffix_of_a_utf8_cell_name_is_unchanged():
    assert _delta_artifact_name("ok") == "plugin-delta-ok-to-p-c90164a3.json"


def _topics_cache_dir(tmp_path, monkeypatch, doc_source: str) -> Path:
    """The ``cache_dir`` the pipeline's question step hands the topic extractor for ``doc_source``."""
    import dokimi.questions as questions
    from dokimi.orchestrator.pipeline import EvaluationPipeline
    from dokimi.registry import ProductRegistry

    seen = {}

    class _StopHere(Exception):
        pass

    class _Extractor:
        def __init__(self, **kwargs):
            seen["cache_dir"] = kwargs["cache_dir"]

        def extract_topics(self, **kwargs):
            raise _StopHere

    class _Client:
        requires_declared_library_id = False

    monkeypatch.setattr("dokimi.orchestrator.pipeline.create_doc_source_client", lambda source: _Client())
    monkeypatch.setattr(questions, "RagasSeedExtractor", _Extractor)
    registry_path = tmp_path / "products.yaml"
    registry_path.write_text("products:\n  my_lib:\n    name: My Lib\n    description: d\n    context7_id: org/lib\n",
                             encoding="utf-8")
    pipeline = EvaluationPipeline(product="My Lib", description="d", product_key="my_lib", output_dir=tmp_path / "run",
                                  registry=ProductRegistry(path=registry_path), doc_source=doc_source)
    with pytest.raises(_StopHere):
        pipeline._generate_questions({})
    return seen["cache_dir"]


@posix_only
def test_pipeline_topics_cache_of_a_doc_source_with_a_non_utf8_byte_gets_its_own_directory(tmp_path, monkeypatch):
    first = _topics_cache_dir(tmp_path, monkeypatch, "url:https://example.com/n\udcff")
    second = _topics_cache_dir(tmp_path, monkeypatch, "url:https://example.com/n\udcfe")
    assert first == Path(".cache/topics/173ffc509215f580")
    assert second == Path(".cache/topics/734bd48df45078ff")


def test_pipeline_topics_cache_of_a_utf8_doc_source_is_unchanged(tmp_path, monkeypatch):
    cache_dir = _topics_cache_dir(tmp_path, monkeypatch, "url:https://example.com/doc")
    assert cache_dir == Path(".cache/topics/782971a1dc6a2ae1")


