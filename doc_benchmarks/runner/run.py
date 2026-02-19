"""Benchmark run orchestration."""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, fields
from pathlib import Path

import yaml

from doc_benchmarks.ingest.chunker import chunk_text
from doc_benchmarks.ingest.loader import discover_markdown, load_docs
from doc_benchmarks.metrics import coverage, freshness_lite, readability
from doc_benchmarks.metrics.example_runner import ExampleResult, score_examples
from doc_benchmarks.gate.soft_gate import check_soft_gate


@dataclass
class DocMetrics:
    """Per-document metric bundle."""

    path: str
    chunks: int
    coverage: float
    freshness_lite: float
    readability: float
    example_pass_rate: float
    score: float


def _weighted_score(doc: dict, weights: dict[str, float], active_metrics: list[str]) -> float:
    """Compute normalized weighted score across active metrics."""
    total_weight = sum(weights[m] for m in active_metrics)
    if total_weight == 0:
        return 0.0
    raw = sum(doc[m] * weights[m] for m in active_metrics)
    return round(raw / total_weight, 4)


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
    example_cfg = spec["metrics"].get("example_pass_rate", {})
    example_enabled = bool(example_cfg.get("enabled", False))
    example_timeout = int(example_cfg.get("timeout", 5))

    active_metrics = ["coverage", "freshness_lite", "readability"]
    if example_enabled:
        active_metrics.append("example_pass_rate")

    docs = discover_markdown(root / "docs")
    loaded = load_docs(docs)

    # Collect per-doc metrics and cached example results
    rows: list[dict] = []
    cached_example_results: list[list[ExampleResult]] = []

    for p in docs:
        text = loaded[str(p)]
        row: dict = {
            "path": str(p.relative_to(root)),
            "chunks": len(chunk_text(text)),
            "coverage": coverage.score(text),
            "freshness_lite": freshness_lite.score(p, spec["metrics"]["freshness_lite"]["max_age_days"]),
            "readability": readability.score(text, spec["metrics"]["readability"]["grade_max"]),
        }

        if example_enabled:
            ex_score, ex_results = score_examples(p, timeout=example_timeout)
            row["example_pass_rate"] = ex_score
            cached_example_results.append(ex_results)
        else:
            row["example_pass_rate"] = 0.0
            cached_example_results.append([])

        row["score"] = _weighted_score(row, weights, active_metrics)
        rows.append(row)

    metric_fields = ["coverage", "freshness_lite", "readability"]
    if example_enabled:
        metric_fields.append("example_pass_rate")

    agg: dict = {
        m: round(sum(r[m] for r in rows) / max(1, len(rows)), 4)
        for m in metric_fields
    }
    total_score = round(sum(r["score"] for r in rows) / max(1, len(rows)), 4)

    docs_out = []
    for row, ex_results in zip(rows, cached_example_results):
        d = {
            "path": row["path"],
            "chunks": row["chunks"],
            "coverage": row["coverage"],
            "freshness_lite": row["freshness_lite"],
            "readability": row["readability"],
            "example_pass_rate": row["example_pass_rate"],
            "score": row["score"],
        }
        if example_enabled:
            d["example_results"] = [
                {"index": r.index, "lang": r.lang, "passed": r.passed, "error": r.error}
                for r in ex_results
            ]
        docs_out.append(d)

    gate_result = check_soft_gate({"score": total_score}, spec)

    return {
        "summary": {"docs": len(rows), "score": total_score, **agg},
        "docs": docs_out,
        "gate": {
            "soft": {
                "enabled": gate_result.enabled,
                "passed": gate_result.passed,
                "min_score": gate_result.min_score,
            }
        },
    }


def save_snapshot(data: dict, out_path: Path) -> None:
    """Persist run snapshot to JSON file."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
