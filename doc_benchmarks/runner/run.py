"""Benchmark run orchestration."""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path

import yaml

from doc_benchmarks.ingest.chunker import chunk_text
from doc_benchmarks.ingest.loader import discover_markdown, load_docs
from doc_benchmarks.metrics import coverage, freshness_lite, readability


@dataclass
class DocMetrics:
    """Per-document metric bundle."""

    path: str
    chunks: int
    coverage: float
    freshness_lite: float
    readability: float
    score: float


def _weighted_score(doc: dict, weights: dict[str, float]) -> float:
    """Compute weighted score from metric values."""
    return round(
        doc["coverage"] * weights["coverage"]
        + doc["freshness_lite"] * weights["freshness_lite"]
        + doc["readability"] * weights["readability"],
        4,
    )


def _load_spec(spec_path: Path) -> dict:
    """Load benchmark spec YAML with explicit, descriptive failures."""
    try:
        content = spec_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"Failed to read spec file: {spec_path}: {exc}") from exc

    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise RuntimeError(f"Invalid YAML in spec file: {spec_path}: {exc}") from exc

    if not isinstance(data, dict):
        raise RuntimeError(f"Spec root must be a mapping/object: {spec_path}")

    missing: list[str] = []
    if "weights" not in data:
        missing.append("weights")
    if "metrics" not in data or not isinstance(data.get("metrics"), dict):
        missing.append("metrics")
    else:
        metrics = data["metrics"]
        if "freshness_lite" not in metrics or "max_age_days" not in metrics.get("freshness_lite", {}):
            missing.append("metrics.freshness_lite.max_age_days")
        if "readability" not in metrics or "grade_max" not in metrics.get("readability", {}):
            missing.append("metrics.readability.grade_max")

    if missing:
        raise RuntimeError(f"Spec missing required fields ({', '.join(missing)}): {spec_path}")

    return data


def run_benchmark(root: Path, spec_path: Path) -> dict:
    """Run benchmark on markdown docs and return snapshot payload."""
    spec = _load_spec(spec_path)
    weights = spec["weights"]

    docs = discover_markdown(root / "docs")
    loaded = load_docs(docs)

    results: list[DocMetrics] = []
    for p in docs:
        text = loaded[str(p)]
        row = {
            "path": str(p.relative_to(root)),
            "chunks": len(chunk_text(text)),
            "coverage": coverage.score(text),
            "freshness_lite": freshness_lite.score(p, spec["metrics"]["freshness_lite"]["max_age_days"]),
            "readability": readability.score(text, spec["metrics"]["readability"]["grade_max"]),
        }
        row["score"] = _weighted_score(row, weights)
        results.append(DocMetrics(**row))

    agg = {
        "coverage": round(sum(r.coverage for r in results) / max(1, len(results)), 4),
        "freshness_lite": round(sum(r.freshness_lite for r in results) / max(1, len(results)), 4),
        "readability": round(sum(r.readability for r in results) / max(1, len(results)), 4),
    }
    total_score = round(sum(r.score for r in results) / max(1, len(results)), 4)

    return {
        "summary": {
            "docs": len(results),
            "score": total_score,
            **agg,
        },
        "docs": [asdict(r) for r in results],
    }


def save_snapshot(data: dict, out_path: Path) -> None:
    """Persist run snapshot to JSON file."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
