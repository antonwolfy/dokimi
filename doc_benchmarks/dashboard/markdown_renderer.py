"""Render DashboardData as Markdown."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from doc_benchmarks.dashboard.aggregator import DashboardData, ProductSnapshot


def _score_bar(score: Optional[float], width: int = 10) -> str:
    if score is None:
        return "·" * width
    filled = round(score / 100 * width)
    return "█" * filled + "░" * (width - filled)


def _status_emoji(status: str) -> str:
    return {"good": "🟢", "fair": "🟡", "poor": "🔴", "no-data": "⚪"}.get(status, "⚪")


def _md_cell(text: str) -> str:
    """Escape pipe and newlines so text is safe inside a Markdown table cell."""
    return text.replace("|", "\\|").replace("\n", " ").replace("\r", "").strip()


def _fmt_delta(delta: Optional[float]) -> str:
    if delta is None:
        return "—"
    return f"+{delta:.1f}" if delta >= 0 else f"{delta:.1f}"


def render_dashboard(data: DashboardData, top_n_bad_questions: int = 5) -> str:
    lines = []
    lines.append("# Doc Benchmark Dashboard")
    lines.append(f"\n_Generated: {data.generated_at}_\n")

    if not data.products:
        lines.append("_No evaluation results found. Run `benchmark batch --all` to generate data._")
        return "\n".join(lines)

    # ── Summary table ──────────────────────────────────────────────────────
    lines.append("## Overview\n")
    lines.append("| Status | Product | With Docs | Without Docs | Delta | Questions | Evaluated |")
    lines.append("|--------|---------|-----------|--------------|-------|-----------|-----------|")

    for p in data.sorted_by_score:
        emoji = _status_emoji(p.status)
        with_s = f"{p.avg_with_docs:.1f}" if p.avg_with_docs is not None else "—"
        without_s = f"{p.avg_without_docs:.1f}" if p.avg_without_docs is not None else "—"
        delta_s = _fmt_delta(p.avg_delta)
        date = p.evaluated_at[:10] if p.evaluated_at else "—"
        lines.append(
            f"| {emoji} | **{_md_cell(p.product)}** | {with_s} | {without_s} | {delta_s} | {p.total_questions} | {date} |"
        )

    # ── Score distribution bar ─────────────────────────────────────────────
    lines.append("\n## Score Distribution\n")
    lines.append("```")
    for p in data.sorted_by_score:
        score = p.doc_score
        bar = _score_bar(score)
        score_str = f"{score:5.1f}" if score is not None else "  n/a"
        lines.append(f"{p.product:<30} {bar} {score_str}")
    lines.append("```")

    # ── Per-product drill-down ─────────────────────────────────────────────
    lines.append("\n## Per-Product Details\n")
    for p in data.sorted_by_score:
        lines.extend(_render_product_section(p, top_n_bad_questions))

    return "\n".join(lines)


def _render_product_section(p: ProductSnapshot, top_n: int) -> list[str]:
    lines = []
    emoji = _status_emoji(p.status)
    lines.append(f"### {emoji} {p.product}\n")

    with_s = f"{p.avg_with_docs:.1f}/100" if p.avg_with_docs is not None else "—"
    without_s = f"{p.avg_without_docs:.1f}/100" if p.avg_without_docs is not None else "—"
    delta_s = _fmt_delta(p.avg_delta)

    lines.append(f"- **Score with docs**: {with_s}")
    lines.append(f"- **Score without docs**: {without_s}")
    lines.append(f"- **Delta (docs benefit)**: {delta_s}")
    lines.append(f"- **Questions evaluated**: {p.total_questions}")
    lines.append(f"- **Judge model**: {p.judge_model}")
    lines.append(f"- **Evaluated**: {p.evaluated_at[:19] if p.evaluated_at else '—'}")

    # Worst questions
    bad = [q for q in p.questions if q.with_docs_score is not None][:top_n]
    if bad:
        lines.append(f"\n**Bottom {len(bad)} questions (needs improvement):**\n")
        lines.append("| Score | Δ | Question |")
        lines.append("|-------|---|---------|")
        for q in bad:
            score = f"{q.with_docs_score:.0f}" if q.with_docs_score is not None else "—"
            delta = _fmt_delta(round(q.delta, 0) if q.delta is not None else None).replace(".0", "")
            question_short = _md_cell(q.question[:80] + ("…" if len(q.question) > 80 else ""))
            lines.append(f"| {score} | {delta} | {question_short} |")

    lines.append("")
    return lines


def save_dashboard_markdown(data: DashboardData, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_dashboard(data))


def save_dashboard_json(data: DashboardData, path: Path) -> None:
    import json
    from dataclasses import asdict
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(data), indent=2))
