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
