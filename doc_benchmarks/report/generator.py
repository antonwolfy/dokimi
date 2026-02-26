"""Generate reports from evaluation results."""

import json
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
from collections import defaultdict
import re

from doc_benchmarks.eval.diagnoser import (
    summarise_diagnoses,
    DIAGNOSIS_LABELS,
    DIAGNOSIS_DESCRIPTIONS,
)

logger = logging.getLogger(__name__)


class ReportGenerator:
    """
    Generate analysis reports from eval results.
    
    Features:
    - Topic clustering (by persona + keywords)
    - Top/bottom performers
    - WITH vs WITHOUT comparison by cluster
    - Identify doc gaps
    """
    
    def __init__(self):
        pass
    
    def generate_report(
        self,
        eval_data: Dict[str, Any],
        questions_data: Dict[str, Any],
        output_format: str = "markdown"
    ) -> str:
        """
        Generate comprehensive report.
        
        Args:
            eval_data: Loaded eval JSON (from Judge)
            questions_data: Loaded questions JSON (for clustering)
            output_format: "markdown" or "json"
        
        Returns:
            Report text (markdown) or JSON string
        """
        evaluations = eval_data.get("evaluations", [])
        questions = questions_data.get("questions", [])
        
        # Build question lookup
        q_lookup = {q["id"]: q for q in questions}
        
        # Overall stats
        stats = self._compute_stats(evaluations)
        
        # Top/bottom performers
        top_with = self._top_performers(evaluations, "with_docs", limit=10)
        bottom_with = self._bottom_performers(evaluations, "with_docs", limit=10)
        
        # Delta analysis
        top_deltas = self._top_deltas(evaluations, limit=10)
        bottom_deltas = self._bottom_deltas(evaluations, limit=10)
        
        # Cluster by topic
        clusters = self._cluster_by_topic(evaluations, q_lookup)

        # Failure analysis
        failure_summary = summarise_diagnoses(evaluations)

        if output_format == "json":
            return json.dumps({
                "stats": stats,
                "top_with_docs": top_with,
                "bottom_with_docs": bottom_with,
                "top_deltas": top_deltas,
                "bottom_deltas": bottom_deltas,
                "clusters": clusters,
                "failure_analysis": failure_summary,
            }, indent=2)
        else:
            return self._format_markdown(
                stats, top_with, bottom_with, top_deltas, bottom_deltas,
                clusters, failure_summary
            )
    
    def _compute_stats(self, evaluations: List[Dict]) -> Dict[str, Any]:
        """Compute overall statistics."""
        with_scores = [e["with_docs"]["aggregate"] for e in evaluations if e.get("with_docs")]
        without_scores = [e["without_docs"]["aggregate"] for e in evaluations if e.get("without_docs")]
        deltas = [e["delta"] for e in evaluations if e.get("delta") is not None]
        
        return {
            "total_questions": len(evaluations),
            "with_docs": {
                "avg": round(sum(with_scores) / len(with_scores), 1) if with_scores else 0,
                "min": round(min(with_scores), 1) if with_scores else 0,
                "max": round(max(with_scores), 1) if with_scores else 0,
            },
            "without_docs": {
                "avg": round(sum(without_scores) / len(without_scores), 1) if without_scores else 0,
                "min": round(min(without_scores), 1) if without_scores else 0,
                "max": round(max(without_scores), 1) if without_scores else 0,
            },
            "delta": {
                "avg": round(sum(deltas) / len(deltas), 1) if deltas else 0,
                "min": round(min(deltas), 1) if deltas else 0,
                "max": round(max(deltas), 1) if deltas else 0,
            },
            "doc_improvements": sum(1 for d in deltas if d > 0),
            "doc_degradations": sum(1 for d in deltas if d < 0),
        }
    
    def _top_performers(self, evaluations: List[Dict], mode: str, limit: int) -> List[Dict]:
        """Get top N by aggregate score."""
        scored = [(e[mode]["aggregate"], e) for e in evaluations if e.get(mode)]
        scored.sort(reverse=True, key=lambda x: x[0])
        return [
            {
                "question_id": e["question_id"],
                "score": s,
                "question_text": e.get("question_text", "")[:80]
            }
            for s, e in scored[:limit]
        ]
    
    def _bottom_performers(self, evaluations: List[Dict], mode: str, limit: int) -> List[Dict]:
        """Get bottom N by aggregate score."""
        scored = [(e[mode]["aggregate"], e) for e in evaluations if e.get(mode)]
        scored.sort(key=lambda x: x[0])
        return [
            {
                "question_id": e["question_id"],
                "score": s,
                "question_text": e.get("question_text", "")[:80]
            }
            for s, e in scored[:limit]
        ]
    
    def _top_deltas(self, evaluations: List[Dict], limit: int) -> List[Dict]:
        """Get top N improvements (WITH - WITHOUT)."""
        deltas = [
            (e["delta"], e)
            for e in evaluations if e.get("delta") is not None
        ]
        deltas.sort(reverse=True, key=lambda x: x[0])
        return [
            {
                "question_id": e["question_id"],
                "delta": d,
                "with_score": e["with_docs"]["aggregate"],
                "without_score": e["without_docs"]["aggregate"],
                "question_text": e.get("question_text", "")[:80]
            }
            for d, e in deltas[:limit]
        ]
    
    def _bottom_deltas(self, evaluations: List[Dict], limit: int) -> List[Dict]:
        """Get bottom N (worst degradations from docs)."""
        deltas = [
            (e["delta"], e)
            for e in evaluations if e.get("delta") is not None
        ]
        deltas.sort(key=lambda x: x[0])
        return [
            {
                "question_id": e["question_id"],
                "delta": d,
                "with_score": e["with_docs"]["aggregate"],
                "without_score": e["without_docs"]["aggregate"],
                "question_text": e.get("question_text", "")[:80]
            }
            for d, e in deltas[:limit]
        ]
    
    def _cluster_by_topic(
        self,
        evaluations: List[Dict],
        q_lookup: Dict[str, Dict]
    ) -> List[Dict[str, Any]]:
        """
        Cluster questions by topic (extracted from persona + keywords).
        
        Returns list of clusters with stats.
        """
        # Extract topics from questions
        topic_map = defaultdict(list)
        
        for e in evaluations:
            qid = e["question_id"]
            q = q_lookup.get(qid, {})
            
            # Use persona as primary cluster
            persona_id = q.get("persona_id", "unknown")
            topic_map[persona_id].append(e)
        
        # Compute stats per cluster
        clusters = []
        for topic, evals in topic_map.items():
            with_scores = [e["with_docs"]["aggregate"] for e in evals if e.get("with_docs")]
            without_scores = [e["without_docs"]["aggregate"] for e in evals if e.get("without_docs")]
            deltas = [e["delta"] for e in evals if e.get("delta") is not None]
            
            clusters.append({
                "topic": topic,
                "count": len(evals),
                "with_avg": round(sum(with_scores) / len(with_scores), 1) if with_scores else 0,
                "without_avg": round(sum(without_scores) / len(without_scores), 1) if without_scores else 0,
                "delta_avg": round(sum(deltas) / len(deltas), 1) if deltas else 0,
            })
        
        # Sort by delta (worst first)
        clusters.sort(key=lambda x: x["delta_avg"])
        
        return clusters
    
    def _format_markdown(
        self,
        stats: Dict,
        top_with: List[Dict],
        bottom_with: List[Dict],
        top_deltas: List[Dict],
        bottom_deltas: List[Dict],
        clusters: List[Dict],
        failure_summary: Optional[Dict] = None,
    ) -> str:
        """Format report as Markdown."""
        lines = [
            "# Documentation Quality Report",
            "",
            f"**Total Questions:** {stats['total_questions']}",
            "",
            "## Overall Statistics",
            "",
            "| Metric | WITH Docs | WITHOUT Docs | Delta |",
            "|--------|-----------|--------------|-------|",
            f"| Average | {stats['with_docs']['avg']} | {stats['without_docs']['avg']} | **{stats['delta']['avg']:+.1f}** |",
            f"| Min | {stats['with_docs']['min']} | {stats['without_docs']['min']} | {stats['delta']['min']:+.1f} |",
            f"| Max | {stats['with_docs']['max']} | {stats['without_docs']['max']} | {stats['delta']['max']:+.1f} |",
            "",
            f"- **Improvements:** {stats['doc_improvements']} questions (docs helped)",
            f"- **Degradations:** {stats['doc_degradations']} questions (docs hurt)",
            "",
            "---",
            "",
            "## Top 10: Best WITH Docs Performance",
            "",
            "| Question ID | Score | Question Text |",
            "|-------------|-------|---------------|",
        ]
        
        for item in top_with:
            lines.append(f"| {item['question_id']} | {item['score']:.1f} | {item['question_text']}... |")
        
        lines.extend([
            "",
            "---",
            "",
            "## Bottom 10: Worst WITH Docs Performance",
            "",
            "| Question ID | Score | Question Text |",
            "|-------------|-------|---------------|",
        ])
        
        for item in bottom_with:
            lines.append(f"| {item['question_id']} | {item['score']:.1f} | {item['question_text']}... |")
        
        lines.extend([
            "",
            "---",
            "",
            "## Top 10: Biggest Improvements (docs helped most)",
            "",
            "| Question ID | Delta | WITH | WITHOUT | Question Text |",
            "|-------------|-------|------|---------|---------------|",
        ])
        
        for item in top_deltas:
            lines.append(
                f"| {item['question_id']} | **+{item['delta']:.1f}** | "
                f"{item['with_score']:.1f} | {item['without_score']:.1f} | "
                f"{item['question_text']}... |"
            )
        
        lines.extend([
            "",
            "---",
            "",
            "## Bottom 10: Biggest Degradations (docs hurt most)",
            "",
            "| Question ID | Delta | WITH | WITHOUT | Question Text |",
            "|-------------|-------|------|---------|---------------|",
        ])
        
        for item in bottom_deltas:
            lines.append(
                f"| {item['question_id']} | **{item['delta']:.1f}** | "
                f"{item['with_score']:.1f} | {item['without_score']:.1f} | "
                f"{item['question_text']}... |"
            )
        
        lines.extend([
            "",
            "---",
            "",
            "## Performance by Topic/Persona",
            "",
            "| Topic | Count | WITH Avg | WITHOUT Avg | Delta |",
            "|-------|-------|----------|-------------|-------|",
        ])
        
        for cluster in clusters:
            lines.append(
                f"| {cluster['topic']} | {cluster['count']} | "
                f"{cluster['with_avg']:.1f} | {cluster['without_avg']:.1f} | "
                f"**{cluster['delta_avg']:+.1f}** |"
            )
        
        # ── Failure Analysis section ─────────────────────────────────────
        if failure_summary:
            lines.extend([
                "",
                "---",
                "",
                "## Failure Analysis",
                "",
                "Breakdown of *why* documentation helped or failed for each question.",
                "",
                "| Diagnosis | Count | Rate | Description |",
                "|-----------|------:|-----:|-------------|",
            ])
            counts = failure_summary.get("counts", {})
            total_q = failure_summary.get("total", 1)
            for label, display in DIAGNOSIS_LABELS.items():
                count = counts.get(label, 0)
                rate = f"{count / total_q:.0%}"
                desc = DIAGNOSIS_DESCRIPTIONS.get(label, "")
                lines.append(f"| {display} | {count} | {rate} | {desc} |")

            # Detail table for failures (delta < 0)
            failures = failure_summary.get("failures", [])
            if failures:
                lines.extend([
                    "",
                    f"### Questions with Negative Delta ({len(failures)} total)",
                    "",
                    "| Question ID | Delta | Diagnosis | Evidence |",
                    "|-------------|------:|-----------|---------|",
                ])
                for e in sorted(failures, key=lambda x: x.get("delta") or 0)[:20]:
                    diag = e.get("diagnosis") or {}
                    label = diag.get("label", "?")
                    display = DIAGNOSIS_LABELS.get(label, label)
                    evidence = diag.get("evidence", {})
                    ev_str = ", ".join(
                        f"{k}={v}" for k, v in evidence.items()
                        if k != "delta" and v is not None
                    )
                    lines.append(
                        f"| {e['question_id']} | **{(e.get('delta') or 0):+.1f}** "
                        f"| {display} | {ev_str} |"
                    )

        lines.extend([
            "",
            "---",
            "",
            "## Recommendations",
            "",
        ])
        
        # Add recommendations based on data
        if stats["delta"]["avg"] < 0:
            lines.append("⚠️ **Overall:** Documentation is hurting answer quality. Consider:")
            lines.append("- Improving retrieval relevance")
            lines.append("- Adding more specific examples to docs")
            lines.append("- Removing outdated/misleading content")
        elif stats["delta"]["avg"] > 2:
            lines.append("✅ **Overall:** Documentation is significantly helping. Continue:")
            lines.append("- Maintaining doc quality")
            lines.append("- Expanding coverage for low-performing topics")
        else:
            lines.append("⚪ **Overall:** Documentation has minimal impact. Consider:")
            lines.append("- Improving doc discoverability")
            lines.append("- Adding more practical examples")
        
        lines.append("")
        
        # Identify worst clusters
        worst_clusters = [c for c in clusters if c["delta_avg"] < -1]
        if worst_clusters:
            lines.append("### Topics Needing Doc Improvements:")
            lines.append("")
            for c in worst_clusters[:5]:
                lines.append(f"- **{c['topic']}** (delta: {c['delta_avg']:+.1f})")
        
        return "\n".join(lines)
