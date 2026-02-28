"""Library registry — load and query known products from libraries.yaml."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

# Default registry bundled with the package
_DEFAULT_REGISTRY = Path(__file__).parent.parent / "libraries.yaml"


@dataclass
class LibraryEntry:
    key: str                          # registry key, e.g. "onetbb"
    name: str                         # human name, e.g. "oneTBB"
    description: str
    repo: Optional[str] = None
    context7_id: Optional[str] = None
    doc_sources: List[str] = field(default_factory=lambda: ["context7"])


class LibraryRegistry:
    """Load and query the libraries.yaml registry."""

    def __init__(self, path: Optional[Path] = None):
        self._path = path or _DEFAULT_REGISTRY
        self._entries: Dict[str, LibraryEntry] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            logger.warning(f"Registry not found: {self._path}")
            return
        data = yaml.safe_load(self._path.read_text()) or {}
        if not isinstance(data, dict) or "libraries" not in data:
            logger.warning(f"Registry {self._path} has no 'libraries' key — skipping.")
            return
        libraries = data["libraries"]
        if not isinstance(libraries, dict):
            logger.warning(f"Registry 'libraries' must be a mapping — skipping.")
            return
        for raw_key, cfg in libraries.items():
            if not isinstance(raw_key, str):
                logger.warning(f"Registry key '{raw_key}' is not a string — skipping.")
                continue
            key = raw_key.lower()
            if key in self._entries:
                logger.warning(
                    f"Registry key collision: '{raw_key}' normalizes to '{key}' "
                    f"which is already registered. Skipping duplicate."
                )
                continue
            if not isinstance(cfg, dict):
                logger.warning(f"Registry entry '{raw_key}' is not a mapping — skipping.")
                continue
            doc_sources = cfg.get("doc_sources", ["context7"])
            if not isinstance(doc_sources, list) or not doc_sources:
                logger.warning(f"Registry entry '{raw_key}' has empty doc_sources — defaulting to context7.")
                doc_sources = ["context7"]
            self._entries[key] = LibraryEntry(
                key=key,
                name=cfg.get("name", raw_key),
                description=str(cfg.get("description") or "").strip(),
                repo=cfg.get("repo"),
                context7_id=cfg.get("context7_id"),
                doc_sources=doc_sources,
            )
        logger.info(f"Loaded {len(self._entries)} libraries from {self._path}")

    def get(self, key: str) -> LibraryEntry:
        """Return entry by key (case-insensitive). Raises KeyError if not found."""
        entry = self._entries.get(key.lower())
        if entry is None:
            available = ", ".join(sorted(self._entries))
            raise KeyError(f"Library '{key}' not found in registry. Available: {available}")
        return entry

    def list(self) -> List[LibraryEntry]:
        return list(self._entries.values())

    def keys(self) -> List[str]:
        return sorted(self._entries.keys())

    def __contains__(self, key: str) -> bool:
        return key.lower() in self._entries
