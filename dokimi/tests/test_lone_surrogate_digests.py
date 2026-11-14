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
