"""Snapshot comparison logic."""

from __future__ import annotations

import json
from pathlib import Path


def compare_snapshots(base_path: Path, cand_path: Path) -> dict:
    """Compare two run snapshots and return summary and metric deltas."""
    try:
        base = json.loads(base_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid base snapshot {base_path}: {exc}") from exc

    try:
        cand = json.loads(cand_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid candidate snapshot {cand_path}: {exc}") from exc

    required = {"docs", "score", "coverage", "freshness_lite", "readability"}
    for path, payload in ((base_path, base), (cand_path, cand)):
        summary = payload.get("summary") if isinstance(payload, dict) else None
        if not isinstance(summary, dict):
            raise ValueError(f"Snapshot missing summary object: {path}")
        missing = required - set(summary.keys())
        if missing:
            raise ValueError(f"Snapshot {path} missing summary keys: {sorted(missing)}")

    diff = {
        "docs": cand["summary"]["docs"] - base["summary"]["docs"],
        "score": round(cand["summary"]["score"] - base["summary"]["score"], 4),
        "coverage": round(cand["summary"]["coverage"] - base["summary"]["coverage"], 4),
        "freshness_lite": round(cand["summary"]["freshness_lite"] - base["summary"]["freshness_lite"], 4),
        "readability": round(cand["summary"]["readability"] - base["summary"]["readability"], 4),
    }
    return {"base": base["summary"], "candidate": cand["summary"], "diff": diff}
