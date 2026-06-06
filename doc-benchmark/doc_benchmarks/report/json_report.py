"""JSON report writers."""

from __future__ import annotations

import json
from pathlib import Path


def write_json(data: dict, path: Path) -> None:
    """Write JSON data to path, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
