"""Shared utilities for MCP doc-source clients."""

import re
from typing import List


def strip_html(text: str) -> str:
    """Remove HTML tags, strip script/style blocks, collapse whitespace."""
    text = re.sub(
        r"<(script|style)[^>]*>.*?</(script|style)>",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def score_chunk(query: str, content: str) -> float:
    """Simple keyword overlap score (0–1)."""
    query_tokens = set(re.findall(r"\w+", query.lower()))
    if not query_tokens:
        return 0.0
    content_lower = content.lower()
    hits = sum(1 for tok in query_tokens if tok in content_lower)
    return hits / len(query_tokens)


def split_paragraphs(text: str, min_len: int = 80) -> List[str]:
    """Split text on blank lines; discard very short chunks."""
    chunks = re.split(r"\n{2,}|\r\n{2,}", text)
    return [c.strip() for c in chunks if len(c.strip()) >= min_len]
