"""Coverage scoring heuristic for markdown docs."""

from __future__ import annotations

import re


HEADING_RE = re.compile(r"^#{1,6}\s+", re.MULTILINE)
CODE_BLOCK_RE = re.compile(r"```", re.MULTILINE)


def score(text: str) -> float:
    """Return simple structure/body coverage score in [0, 1]."""
    if not text.strip():
        return 0.0
    headings = len(HEADING_RE.findall(text))
    code_blocks = len(CODE_BLOCK_RE.findall(text)) // 2
    words = len(text.split())

    heading_signal = min(headings / 6.0, 1.0)
    code_signal = min(code_blocks / 3.0, 1.0)
    body_signal = min(words / 500.0, 1.0)

    return round(0.4 * heading_signal + 0.3 * code_signal + 0.3 * body_signal, 4)
