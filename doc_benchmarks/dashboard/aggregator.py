"""Aggregate evaluation results from results/ directory into dashboard data."""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class QuestionResult:
    question_id: str
    question: str
    with_docs_score: Optional[float]
    without_docs_score: Optional[float]
    delta: Optional[float]
    # Per-dimension scores
    with_docs_dimensions: Dict[str, float] = field(default_factory=dict)
    without_docs_dimensions: Dict[str, float] = field(default_factory=dict)


@dataclass
class ProductSnapshot:
    """Aggregated results for one product / one evaluation run."""
    product: str                       # e.g. "oneTBB"
    library_key: str                   # e.g. "onetbb"
    evaluated_at: str
    judge_model: str
    total_questions: int
    avg_with_docs: Optional[float]
    avg_without_docs: Optional[float]
    avg_delta: Optional[float]
    questions: List[QuestionResult] = field(default_factory=list)
    source_file: Optional[str] = None

    @property
    def doc_score(self) -> Optional[float]:
        """Primary score: avg with_docs (or without_docs if no docs run)."""
        return self.avg_with_docs if self.avg_with_docs is not None else self.avg_without_docs

    @property
    def status(self) -> str:
        if self.doc_score is None:
            return "no-data"
        if self.doc_score >= 75:
            return "good"
        if self.doc_score >= 50:
            return "fair"
        return "poor"


@dataclass
class DashboardData:
    generated_at: str
    products: List[ProductSnapshot] = field(default_factory=list)

    @property
    def sorted_by_score(self) -> List[ProductSnapshot]:
        return sorted(
            self.products,
            key=lambda p: p.doc_score if p.doc_score is not None else -1,
            reverse=True,
        )


class ResultsAggregator:
    """Scan a results directory and build DashboardData."""

    def __init__(self, results_dir: Path):
        self.results_dir = results_dir

    def aggregate(self) -> DashboardData:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        snapshots = []

        if not self.results_dir.exists():
            logger.warning(f"Results directory not found: {self.results_dir}")
            return DashboardData(generated_at=now, products=[])

        # Find all eval JSON files matching orchestrator output pattern (eval/{product}.json)
        eval_files = list(self.results_dir.rglob("eval/*.json")) + \
                     list(self.results_dir.rglob("eval_*.json")) + \
                     list(self.results_dir.rglob("evaluations/*.json"))

        # Deduplicate
        seen = set()
        unique_files = []
        for f in eval_files:
            if f not in seen:
                seen.add(f)
                unique_files.append(f)

        for eval_file in sorted(unique_files):
            snapshot = self._load_snapshot(eval_file)
            if snapshot:
                snapshots.append(snapshot)

        return DashboardData(generated_at=now, products=snapshots)

    def _load_snapshot(self, path: Path) -> Optional[ProductSnapshot]:
        try:
            data = json.loads(path.read_text())
        except Exception as e:
            logger.warning(f"Cannot read {path}: {e}")
            return None

        if not isinstance(data, dict):
            logger.warning(f"Invalid snapshot format in {path}: expected JSON object")
            return None

        evaluations = data.get("evaluations", [])
        if not isinstance(evaluations, list):
            logger.warning(f"Invalid evaluations format in {path}: expected list")
            return None
        if not evaluations:
            return None

        # Infer product name: prefer explicit field, fall back to filename stem
        product = data.get("library_name") or data.get("product") or path.stem
        library_key = product.lower().replace(" ", "").replace("-", "")

        def _as_float(value: Any) -> Optional[float]:
            try:
                if value is None:
                    return None
                v = float(value)
                return v if math.isfinite(v) else None
            except (TypeError, ValueError):
                return None

        questions = []
        with_scores = []
        without_scores = []
        deltas = []

        for ev in evaluations:
            if not isinstance(ev, dict):
                continue
            q_id = ev.get("question_id", "")
            q_text = ev.get("question_text") or ev.get("question", "")

            with_eval = ev.get("with_docs") or {}
            without_eval = ev.get("without_docs") or {}

            with_score = _as_float(with_eval.get("aggregate") if isinstance(with_eval, dict) else None)
            without_score = _as_float(without_eval.get("aggregate") if isinstance(without_eval, dict) else None)
            delta = _as_float(ev.get("delta"))

            if with_score is not None:
                with_scores.append(with_score)
            if without_score is not None:
                without_scores.append(without_score)
            if delta is not None:
                deltas.append(delta)

            questions.append(QuestionResult(
                question_id=q_id,
                question=q_text,
                with_docs_score=with_score,
                without_docs_score=without_score,
                delta=delta,
                with_docs_dimensions={k: v for k, v in with_eval.items()
                                      if isinstance(v, (int, float)) and k != "aggregate"},
                without_docs_dimensions={k: v for k, v in without_eval.items()
                                         if isinstance(v, (int, float)) and k != "aggregate"},
            ))

        return ProductSnapshot(
            product=product,
            library_key=library_key,
            evaluated_at=data.get("evaluated_at", ""),
            judge_model=data.get("judge_model", "unknown"),
            total_questions=len(questions),
            avg_with_docs=round(sum(with_scores) / len(with_scores), 1) if with_scores else None,
            avg_without_docs=round(sum(without_scores) / len(without_scores), 1) if without_scores else None,
            avg_delta=round(sum(deltas) / len(deltas), 1) if deltas else None,
            questions=sorted(questions, key=lambda q: (q.with_docs_score or 0)),  # worst first
            source_file=str(path),
        )
