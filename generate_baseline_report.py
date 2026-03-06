#!/usr/bin/env python3
"""
generate_baseline_report.py — Report for libraries without documentation retrieval.

Shows only baseline (WITHOUT docs) model scores — no delta analysis.

Usage:
    python generate_baseline_report.py \
        --eval results/onemkl_sonnet46/eval/oneMKL.json \
        --out results/onemkl_sonnet46/reports/oneMKL_baseline.md
"""

import argparse
import json
import os
from collections import defaultdict
from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo("America/Los_Angeles")
except ImportError:
    _TZ = None

DIFFICULTY_ORDER = ["easy", "beginner", "intermediate", "medium", "advanced", "hard"]

STATIC_PREFIXES = ["onedal-Q", "onetbb-Q", "onednn-Q", "onemkl-Q"]


def is_static(qid):
    return any(qid.startswith(p) for p in STATIC_PREFIXES)


def avg(lst):
    return round(sum(lst) / len(lst), 1) if lst else 0.0


def fmt_question(text):
    if text is None:
        return ""
    return str(text).replace("\n", " ").replace("|", "\\|").strip()


def generate_baseline_report(eval_path: str, out_path: str):
    with open(eval_path) as f:
        data = json.load(f)

    evals = data["evaluations"]
    meta = data.get("run_metadata", {})
    library = os.path.basename(eval_path).replace(".json", "")

    # Extract baseline scores
    valid = [
        e for e in evals
        if e.get("without_docs") and e["without_docs"].get("aggregate") is not None
    ]
    scores = [e["without_docs"]["aggregate"] for e in valid]

    static_qs = [e for e in valid if is_static(e["question_id"])]
    dynamic_qs = [e for e in valid if not is_static(e["question_id"])]

    ts = datetime.now(tz=_TZ).strftime("%Y-%m-%d %H:%M %Z") if _TZ else datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        f"# {library} Baseline Model Knowledge Report",
        f"_Generated: {ts}_",
        "",
        "> **No documentation retrieval available for this library.**",
        "> This report shows raw model performance (WITHOUT docs) only — no delta analysis.",
        "",
        "## Run Configuration",
        "| | |",
        "|---|---|",
        f'| Answer model | {meta.get("answer_model", "—")} ({meta.get("answer_provider", "—")}) |',
        f'| Judge model | {data.get("judge_model", "—")} ({data.get("judge_provider", "—")}) |',
        f'| Total questions | {len(valid)} ({len(dynamic_qs)} dynamic + {len(static_qs)} golden static) |',
        f'| Documentation | ⚠️ Not available (retrieval returned empty/unusable content) |',
        "",
        "## How to Read This Report",
        "",
        "Each answer is scored **0–100** by the judge model across 5 dimensions: "
        "correctness, completeness, specificity, code quality, actionability.",
        "",
        "Since no usable documentation was retrieved, scores reflect **pure model knowledge** only. "
        "This serves as a baseline — if documentation becomes available, re-run to measure its impact.",
        "",
    ]

    # Overall summary
    lines += [
        "## Summary",
        "| Set | Count | Avg Score | Min | Max |",
        "|---|---:|---:|---:|---:|",
        f"| **All** | {len(valid)} | **{avg(scores)}** | {min(scores)} | {max(scores)} |",
        f"| Dynamic (generated) | {len(dynamic_qs)} | {avg([e['without_docs']['aggregate'] for e in dynamic_qs])} | "
        f"{min((e['without_docs']['aggregate'] for e in dynamic_qs), default=0)} | "
        f"{max((e['without_docs']['aggregate'] for e in dynamic_qs), default=0)} |",
        f"| Golden (static) | {len(static_qs)} | {avg([e['without_docs']['aggregate'] for e in static_qs])} | "
        f"{min((e['without_docs']['aggregate'] for e in static_qs), default=0)} | "
        f"{max((e['without_docs']['aggregate'] for e in static_qs), default=0)} |",
        "",
    ]

    # Score distribution
    brackets = [(90, 100, "90–100 (excellent)"), (80, 89, "80–89 (good)"),
                (70, 79, "70–79 (adequate)"), (60, 69, "60–69 (weak)"),
                (0, 59, "0–59 (poor)")]
    lines += [
        "## Score Distribution",
        "| Range | Count | % |",
        "|---|---:|---:|",
    ]
    for lo, hi, label in brackets:
        c = sum(1 for s in scores if lo <= s <= hi)
        lines.append(f"| {label} | {c} | {round(c / len(scores) * 100)}% |")
    lines.append("")

    # By difficulty
    diff_groups = defaultdict(list)
    for e in valid:
        diff_groups[e.get("difficulty", "unknown")].append(e["without_docs"]["aggregate"])

    lines += [
        "## By Difficulty",
        "| Difficulty | Count | Avg Score | Min | Max |",
        "|---|---:|---:|---:|---:|",
    ]
    for d in DIFFICULTY_ORDER:
        if d in diff_groups:
            ss = diff_groups[d]
            lines.append(f"| {d} | {len(ss)} | {avg(ss)} | {min(ss)} | {max(ss)} |")
    lines.append("")

    # Weakest questions (bottom 15)
    lines += [
        "## Weakest Questions (lowest baseline scores)",
        "_These are the questions the model struggles with most — potential documentation targets._",
        "",
        "| QID | Source | Score | Difficulty | Question |",
        "|---|---|---:|---|---|",
    ]
    for e in sorted(valid, key=lambda x: x["without_docs"]["aggregate"])[:15]:
        src = "🔵 static" if is_static(e["question_id"]) else "🟡 gen"
        lines.append(
            f'| {e["question_id"]} | {src} | **{e["without_docs"]["aggregate"]}** '
            f'| {e.get("difficulty", "—")} | {fmt_question(e.get("question_text", ""))} |'
        )
    lines.append("")

    # Strongest questions (top 15)
    lines += [
        "## Strongest Questions (highest baseline scores)",
        "| QID | Source | Score | Difficulty | Question |",
        "|---|---|---:|---|---|",
    ]
    for e in sorted(valid, key=lambda x: x["without_docs"]["aggregate"], reverse=True)[:15]:
        src = "🔵 static" if is_static(e["question_id"]) else "🟡 gen"
        lines.append(
            f'| {e["question_id"]} | {src} | **{e["without_docs"]["aggregate"]}** '
            f'| {e.get("difficulty", "—")} | {fmt_question(e.get("question_text", ""))} |'
        )
    lines.append("")

    # Full table — static
    lines += [
        "## Full Q&A Table — Golden Static Questions",
        "| QID | Score | Difficulty | Question |",
        "|---|---:|---|---|",
    ]
    for e in sorted(static_qs, key=lambda x: (x.get("difficulty", ""), x["question_id"])):
        lines.append(
            f'| {e["question_id"]} | {e["without_docs"]["aggregate"]} '
            f'| {e.get("difficulty", "—")} | {fmt_question(e.get("question_text", ""))} |'
        )
    lines.append("")

    # Full table — dynamic
    lines += [
        "## Full Q&A Table — Dynamic Generated Questions",
        "| QID | Score | Difficulty | Question |",
        "|---|---:|---|---|",
    ]
    for e in sorted(dynamic_qs, key=lambda x: (x.get("difficulty", ""), x["question_id"])):
        lines.append(
            f'| {e["question_id"]} | {e["without_docs"]["aggregate"]} '
            f'| {e.get("difficulty", "—")} | {fmt_question(e.get("question_text", ""))} |'
        )
    lines.append("")

    # Key observations
    weak_count = sum(1 for s in scores if s < 70)
    lines += [
        "## Key Observations",
        "",
        f"- **Average baseline score: {avg(scores)}** — model has {'strong' if avg(scores) >= 85 else 'moderate' if avg(scores) >= 70 else 'weak'} "
        f"pre-existing knowledge of {library}.",
        f"- **{weak_count} questions scored below 70** — these are candidates where documentation could have the most impact.",
        f"- No documentation retrieval was available, so these scores represent a pure knowledge baseline.",
        f"- To measure documentation impact, re-run with a working doc source and compare.",
        "",
    ]

    report = "\n".join(lines)
    dir_path = os.path.dirname(out_path)
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)
    with open(out_path, "w") as f:
        f.write(report)

    print(f"✅ Baseline report written to: {out_path}")
    print(f"   Questions: {len(valid)} ({len(dynamic_qs)} dynamic + {len(static_qs)} static)")
    print(f"   Avg baseline score: {avg(scores)}")
    return out_path


def main():
    parser = argparse.ArgumentParser(description="Generate baseline (no-docs) report from eval JSON.")
    parser.add_argument("--eval", required=True, help="Path to eval JSON file")
    parser.add_argument("--out", required=True, help="Output markdown path")
    args = parser.parse_args()
    generate_baseline_report(args.eval, args.out)


if __name__ == "__main__":
    main()
