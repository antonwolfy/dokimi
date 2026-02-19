"""Markdown report renderers."""

from __future__ import annotations

from pathlib import Path


def _summary_lines(summary: dict) -> list[str]:
    """Render run summary lines in a consistent fixed-precision format."""
    return [
        f"- docs: {summary['docs']}",
        f"- score: {summary['score']:.4f}",
        f"- coverage: {summary['coverage']:.4f}",
        f"- freshness_lite: {summary['freshness_lite']:.4f}",
        f"- readability: {summary['readability']:.4f}",
    ]


def write_run_report(run_data: dict, path: Path) -> None:
    """Write markdown report for a benchmark run."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Doc Benchmark Run", "", "## Summary", *(_summary_lines(run_data["summary"])), "", "## Docs"]
    for d in run_data["docs"]:
        lines.append(
            f"- {d['path']}: score={d['score']:.4f} cov={d['coverage']:.4f} "
            f"fresh={d['freshness_lite']:.4f} read={d['readability']:.4f} chunks={d['chunks']}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_compare_report(compare_data: dict, path: Path) -> None:
    """Write markdown report for snapshot comparison."""
    path.parent.mkdir(parents=True, exist_ok=True)
    d = compare_data["diff"]
    lines = [
        "# Doc Benchmark Compare",
        "",
        "## Diff",
        f"- docs: {d['docs']:+d}",
        f"- score: {d['score']:+.4f}",
        f"- coverage: {d['coverage']:+.4f}",
        f"- freshness_lite: {d['freshness_lite']:+.4f}",
        f"- readability: {d['readability']:+.4f}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
