# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""A console that cannot encode a printed character does not end the command."""

from __future__ import annotations

import io
import sys

from dokimi.console import tolerate_console_encoding


def test_cp1252_console_prints_instead_of_crashing(monkeypatch):
    out = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", newline="\n")
    monkeypatch.setattr(sys, "stdout", out)
    tolerate_console_encoding()
    print("✓ ok")
    out.flush()
    assert out.buffer.getvalue() == b"? ok\n"
