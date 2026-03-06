#!/usr/bin/env python3
"""
compare_models.py — Compare eval results across different answer models.

Usage:
    python compare_models.py \
        --evals deepseek=results/onedal_final/eval/oneDAL.json \
                gpt4o=results/onedal_gpt4o/eval/oneDAL.json \
        --out results/onedal_compare.md
"""

import argparse
import json
import math
import os
from collections import defaultdict
from datetime import datetime, timezone

try:
    from scipy import stats as sp_stats
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

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


def has_scores(e):
    return (
        e.get("with_docs") and e["with_docs"].get("aggregate") is not None
        and e.get("without_docs") and e["without_docs"].get("aggregate") is not None
        and isinstance(e.get("delta"), (int, float))
        and not math.isnan(e["delta"])
    )


def load_eval(path):
    with open(path) as f:
        data = json.load(f)
    evals = {e["question_id"]: e for e in data["evaluations"]}
    meta = data.get("run_metadata", {})
    return data, evals, meta


def model_label(meta):
    m = meta.get("answer_model", "unknown")
    p = meta.get("answer_provider", "")
    return f"{m} ({p})" if p else m


def compute_stats(evals_dict):
    valid = [e for e in evals_dict.values() if has_scores(e)]
    with_s = [e["with_docs"]["aggregate"] for e in valid]
    without_s = [e["without_docs"]["aggregate"] for e in valid]
    deltas = [e["delta"] for e in valid]
    return {
        "n": len(valid),
        "with_avg": avg(with_s),
        "without_avg": avg(without_s),
        "delta_avg": round(avg(with_s) - avg(without_s), 1),
        "improvements": sum(1 for d in deltas if d > 0),
        "degradations": sum(1 for d in deltas if d < 0),
        "neutral": sum(1 for d in deltas if d == 0),
    }


def generate_comparison(runs: dict, out_path: str):
    """
    runs: dict of {label: path}
    """
    loaded = {}
    for label, path in runs.items():
        data, evals, meta = load_eval(path)
        loaded[label] = {"data": data, "evals": evals, "meta": meta}

    # Common questions
    common_ids = set.intersection(*[set(v["evals"].keys()) for v in loaded.values()])
    common_valid = [
        qid for qid in common_ids
        if all(has_scores(loaded[lbl]["evals"][qid]) for lbl in loaded)
    ]

    lines = []
    ts = datetime.now(tz=_TZ).strftime("%Y-%m-%d %H:%M %Z") if _TZ else datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    labels = list(loaded.keys())
    library = list(loaded.values())[0]["data"].get("evaluations", [{}])[0].get("library_name", "")

    lines += [
        f"# {library} Model Comparison Report",
        f"_Generated: {ts}_",
        "",
        "## Models Compared",
        "| Run ID | Answer model | Judge model |",
        "|---|---|---|",
    ]
    question_hashes = {}
    for lbl, v in loaded.items():
        m = v["meta"]
        jp = v["data"].get("judge_provider", "?")
        # normalize naming for consistency in reports
        if jp in ("google", "gemini"):
            jp = "google-vertex"
        lines.append(
            f'| **{lbl}** | {m.get("answer_model","?")} ({m.get("answer_provider","?")}) '
            f'| {v["data"].get("judge_model","?")} ({jp}) |'
        )
        question_hashes[lbl] = m.get("question_set_hash")

    # Reproducibility guardrail: all compared runs must use the same question set
    unique_hashes = {h for h in question_hashes.values() if h}
    lines += ["", "### Question Set Consistency", "", "| Run ID | Question Set ID |", "|---|---|",]
    for lbl in labels:
        lines.append(f"| **{lbl}** | `{question_hashes.get(lbl) or 'missing'}` |")
    if len(unique_hashes) > 1:
        lines += [
            "",
            "⚠️ **Warning:** compared runs use DIFFERENT `question_set_hash` values. "
            "Cross-model comparison may be unfair.",
        ]
    elif len(unique_hashes) == 1:
        lines += ["", f"✅ All runs use the same question set: `{next(iter(unique_hashes))}`"]
    else:
        lines += ["", "ℹ️ Question Set ID missing in metadata for all runs."]

    lines += ["", f"Common questions evaluated: **{len(common_valid)}**", ""]

    # --- Overall summary ---
    lines += [
        "## Overall Summary",
        "| Run | N | WITH docs | WITHOUT docs | Delta | Improved | Degraded |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for lbl, v in loaded.items():
        s = compute_stats(v["evals"])
        lines.append(
            f'| **{lbl}** | {s["n"]} | {s["with_avg"]} | {s["without_avg"]} '
            f'| **{s["delta_avg"]:+}** | {s["improvements"]} | {s["degradations"]} |'
        )
    lines.append("")

    # --- Statistical significance per model ---
    if HAS_SCIPY:
        lines += [
            "## Statistical Significance of Delta (α = 0.05)",
            "_Is each model's delta (WITH − WITHOUT) statistically meaningful?_",
            "",
            "| Run | Delta | p (t-test) | p (Wilcoxon) | Cohen's d | Effect | Significant? |",
            "|---|---:|---:|---:|---:|---|---|",
        ]
        for lbl, v in loaded.items():
            valid_evals = [e for e in v["evals"].values() if has_scores(e)]
            with_s = [e["with_docs"]["aggregate"] for e in valid_evals]
            without_s = [e["without_docs"]["aggregate"] for e in valid_evals]
            deltas_list = [w - wo for w, wo in zip(with_s, without_s)]
            if len(deltas_list) < 5:
                continue
            d_mean = sum(deltas_list) / len(deltas_list)
            d_std = (sum((x - d_mean) ** 2 for x in deltas_list) / len(deltas_list)) ** 0.5
            t_stat, p_t = sp_stats.ttest_rel(with_s, without_s)
            try:
                _, p_w = sp_stats.wilcoxon(deltas_list)
            except Exception:
                p_w = 1.0
            cd = d_mean / d_std if d_std > 0 else 0
            effect = "negligible" if abs(cd) < 0.2 else "small" if abs(cd) < 0.5 else "medium" if abs(cd) < 0.8 else "large"
            sig_mark = "✅ Yes" if p_t < 0.05 else "❌ No"
            lines.append(f"| **{lbl}** | {d_mean:+.1f} | {p_t:.4f} | {p_w:.4f} | {cd:+.3f} | {effect} | {sig_mark} |")
        lines.append("")

    # --- Static vs Dynamic ---
    lines += [
        "## Static (Golden) vs Dynamic",
        "| Run | Type | N | WITH | WITHOUT | Delta |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for lbl, v in loaded.items():
        for qtype, fn in [("🔵 static", is_static), ("🟡 dynamic", lambda qid: not is_static(qid))]:
            subset = {qid: e for qid, e in v["evals"].items() if fn(qid) and has_scores(e)}
            s = compute_stats(subset)
            lines.append(f'| **{lbl}** | {qtype} | {s["n"]} | {s["with_avg"]} | {s["without_avg"]} | **{s["delta_avg"]:+}** |')
    lines.append("")

    # --- By difficulty (on common questions) ---
    lines += [
        "## By Difficulty (common questions only)",
        "| Difficulty | N | " + " | ".join(f"{lbl} WITH | {lbl} Δ" for lbl in labels) + " |",
        "|---|---:|" + "|---:|---:" * len(labels) + "|",
    ]
    diff_groups = defaultdict(list)
    for qid in common_valid:
        diff = loaded[labels[0]]["evals"][qid].get("difficulty", "unknown")
        diff_groups[diff].append(qid)

    for diff in DIFFICULTY_ORDER:
        if diff not in diff_groups:
            continue
        qids = diff_groups[diff]
        row = f"| {diff} | {len(qids)} |"
        for lbl in labels:
            ws = [loaded[lbl]["evals"][qid]["with_docs"]["aggregate"] for qid in qids]
            wos = [loaded[lbl]["evals"][qid]["without_docs"]["aggregate"] for qid in qids]
            w = avg(ws)
            delta = round(w - avg(wos), 1)
            row += f" {w} | {delta:+} |"
        lines.append(row)
    lines.append("")

    # --- Head-to-head on common questions ---
    win_counts = defaultdict(int)
    for qid in common_valid:
        scores = {lbl: loaded[lbl]["evals"][qid]["with_docs"]["aggregate"] for lbl in labels}
        best_score = max(scores.values())
        winners = [lbl for lbl, s in scores.items() if s == best_score]
        if len(winners) == 1:
            win_counts[winners[0]] += 1
        else:
            win_counts["tie"] += 1

    lines += [
        "## Head-to-Head (WITH docs, common questions)",
        "| Winner | Count | % |",
        "|---|---:|---:|",
    ]
    total_common = len(common_valid)
    for lbl in labels:
        c = win_counts[lbl]
        lines.append(f"| **{lbl}** | {c} | {round(c/total_common*100)}% |")
    c = win_counts["tie"]
    lines.append(f"| tie | {c} | {round(c/total_common*100)}% |")
    lines.append("")

    # --- Delta comparison (which model benefits more from docs) ---
    lines += [
        "## Doc Retrieval Benefit — Delta Comparison",
        "_Which model benefits more from documentation context?_",
        "",
        "| Run | Avg Delta | Questions docs helped | Questions docs hurt |",
        "|---|---:|---:|---:|",
    ]
    summaries = {lbl: compute_stats(v["evals"]) for lbl, v in loaded.items()}
    for lbl in sorted(labels, key=lambda l: summaries[l]["delta_avg"], reverse=True):
        s = summaries[lbl]
        lines.append(f'| **{lbl}** | **{s["delta_avg"]:+}** | {s["improvements"]} ({round(s["improvements"]/s["n"]*100)}%) | {s["degradations"]} ({round(s["degradations"]/s["n"]*100)}%) |')
    lines.append("")

    # --- Model ranking ---
    lines += [
        "## Model Ranking",
        "",
        "### By absolute quality (WITH docs)",
        "| Rank | Run | WITH docs avg |",
        "|---:|---|---:|",
    ]
    for i, lbl in enumerate(sorted(labels, key=lambda l: summaries[l]["with_avg"], reverse=True), start=1):
        lines.append(f"| {i} | **{lbl}** | {summaries[lbl]['with_avg']} |")

    lines += [
        "",
        "### By retrieval utilisation (Delta)",
        "| Rank | Run | Delta |",
        "|---:|---|---:|",
    ]
    for i, lbl in enumerate(sorted(labels, key=lambda l: summaries[l]["delta_avg"], reverse=True), start=1):
        lines.append(f"| {i} | **{lbl}** | {summaries[lbl]['delta_avg']:+} |")
    lines.append("")

    # --- Baseline weak spots per model (absolute WITHOUT score) ---
    lines += [
        "## Baseline Weak Spots by Model (WITHOUT docs absolute score)",
        "_Lowest absolute baseline scores per model (not delta)._",
        "",
    ]
    for lbl in labels:
        model_rows = []
        for qid in common_valid:
            e = loaded[lbl]["evals"][qid]
            model_rows.append((qid, e["without_docs"]["aggregate"], e))
        lines += [
            f"### {lbl}",
            "| QID | WITHOUT score | WITH score | Delta | Difficulty | Question |",
            "|---|---:|---:|---:|---|---|",
        ]
        for qid, without_abs, e in sorted(model_rows, key=lambda x: x[1])[:10]:
            q = str(e.get("question_text", "")).replace("|", "\\|").replace("\n", " ")
            lines.append(
                f"| {qid} | **{without_abs}** | {e['with_docs']['aggregate']} | {e['delta']:+.1f} | {e.get('difficulty','—')} | {q} |"
            )
        lines.append("")

    # --- Questions with highest disagreement across models ---
    lines += [
        "## Questions with Highest Model Disagreement (WITH docs)",
        "_These questions separate model capabilities most strongly._",
        "",
        "| QID | Diff | Min score | Max score | Spread | Question |",
        "|---|---|---:|---:|---:|---|",
    ]
    spread_rows = []
    for qid in common_valid:
        scores = [loaded[lbl]["evals"][qid]["with_docs"]["aggregate"] for lbl in labels]
        spread_rows.append((qid, min(scores), max(scores), max(scores) - min(scores), loaded[labels[0]]["evals"][qid]))

    for qid, min_s, max_s, spread, e in sorted(spread_rows, key=lambda x: -x[3])[:15]:
        q = str(e.get("question_text", "")).replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {qid} | {e.get('difficulty','—')} | {min_s:.1f} | {max_s:.1f} | **{spread:.1f}** | {q} |")
    lines.append("")

    # --- Overall analysis ---
    best_with = max(labels, key=lambda l: summaries[l]["with_avg"])
    best_delta = max(labels, key=lambda l: summaries[l]["delta_avg"])
    worst_delta = min(labels, key=lambda l: summaries[l]["delta_avg"])

    lines += [
        "## Overall Analysis & Assessment",
        "",
        f"- **Best absolute quality (WITH docs):** {best_with} ({summaries[best_with]['with_avg']})",
        f"- **Best documentation utilisation (delta):** {best_delta} ({summaries[best_delta]['delta_avg']:+})",
        f"- **Weakest retrieval utilisation:** {worst_delta} ({summaries[worst_delta]['delta_avg']:+})",
        "- **Interpretation:** Use WITH docs score to rank raw model answer quality; use Delta to evaluate documentation/retrieval contribution.",
        "",
        "### Per-model assessment",
        "",
    ]
    for lbl in sorted(labels, key=lambda l: summaries[l]["with_avg"], reverse=True):
        s = summaries[lbl]
        stance = "strong absolute model" if s["with_avg"] >= 84 else "mid absolute model"
        retrieval = "docs help" if s["delta_avg"] > 1 else ("docs neutral" if s["delta_avg"] >= -1 else "docs hurt")
        lines.append(f"- **{lbl}:** WITH={s['with_avg']}, WITHOUT={s['without_avg']}, Δ={s['delta_avg']:+} → {stance}; {retrieval}.")
    lines.append("")

    report = "\n".join(lines)
    dir_path = os.path.dirname(out_path)
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)
    with open(out_path, "w") as f:
        f.write(report)

    print(f"✅ Comparison report: {out_path}")
    print(f"   Common questions: {len(common_valid)}")
    for lbl, v in loaded.items():
        s = summaries[lbl]
        print(f"   {lbl}: with={s['with_avg']} without={s['without_avg']} delta={s['delta_avg']:+}")
    return out_path


def main():
    parser = argparse.ArgumentParser(description="Compare eval results across answer models.")
    parser.add_argument("--evals", nargs="+", required=True,
                        metavar="LABEL=PATH",
                        help="One or more label=path pairs, e.g. deepseek=results/onedal_final/eval/oneDAL.json")
    parser.add_argument("--out", required=True, help="Output markdown path")
    args = parser.parse_args()

    runs = {}
    for item in args.evals:
        if "=" not in item:
            parser.error(f"Expected label=path, got: {item}")
        label, path = item.split("=", 1)
        runs[label] = path

    if len(runs) < 2:
        parser.error("Need at least 2 runs to compare")

    generate_comparison(runs, args.out)


if __name__ == "__main__":
    main()
