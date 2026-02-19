"""Markdown discovery and loading helpers."""

from pathlib import Path
from typing import Iterable


def discover_markdown(root: Path) -> list[Path]:
    """Return sorted markdown files under ``root``."""
    return sorted(p for p in root.rglob("*.md") if p.is_file())


def load_text(path: Path) -> str:
    """Load a UTF-8 text file, replacing invalid bytes."""
    return path.read_text(encoding="utf-8", errors="replace")


def load_docs(paths: Iterable[Path]) -> dict[str, str]:
    """Load all documents into a deterministic path->text mapping."""
    return {str(p): load_text(p) for p in sorted(paths)}
