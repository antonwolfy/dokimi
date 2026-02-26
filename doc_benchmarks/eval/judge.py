"""Judge answers using LLM-as-judge approach."""

import logging
import json
import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

from doc_benchmarks.llm import llm_call, ChatOpenAI, ChatAnthropic, LANGCHAIN_AVAILABLE
from doc_benchmarks.eval.diagnoser import diagnose


JUDGE_PROMPT = """You are evaluating the quality of an answer to a technical question.

**Question:** {question}

**Answer:** {answer}

**Context (if available):**
{context}

**Evaluation criteria:**

1. **Correctness (0-100):** Is the answer factually accurate?
2. **Completeness (0-100):** Does it fully address the question?
3. **Specificity (0-100):** Is it specific to {library_name} (not generic)?
4. **Code Quality (0-100):** If code is included, is it correct and runnable?
5. **Actionability (0-100):** Can the user apply this immediately?

**Instructions:**
- Score each dimension 0-100
- Aggregate score is the average of all 5 dimensions
- Provide brief reasoning for each score

**Output format (JSON only, no other text):**
{{
  "correctness": 85,
  "completeness": 90,
  "specificity": 80,
  "code_quality": 85,
  "actionability": 90,
  "aggregate": 86,
  "reasoning": {{
    "correctness": "Answer is accurate according to docs",
    "completeness": "Covers main aspects",
    "specificity": "Uses {library_name}-specific APIs",
    "code_quality": "Code compiles and follows best practices",
    "actionability": "Clear steps provided"
  }}
}}"""


class Judge:
    """
    Evaluate answer quality using LLM-as-judge.
    
    Scores answers on 5 dimensions (0-100):
    - Correctness
    - Completeness
    - Specificity
    - Code Quality
    - Actionability
    """
    
    def __init__(
        self,
        model: str = "claude-sonnet-4",
        provider: str = "anthropic",
        api_key: Optional[str] = None
    ):
        """
        Args:
            model: LLM model for judging (should differ from answerer model)
            provider: "openai" or "anthropic"
            api_key: Optional API key
        """
        if not LANGCHAIN_AVAILABLE:
            raise ImportError(
                "LLM dependencies not available. "
                "Install: pip install litellm"
            )

        self.model = model
        self.provider = provider
        self.api_key = api_key

        if provider == "openai":
            self.llm = ChatOpenAI(model=model, api_key=api_key)
        elif provider == "anthropic":
            self.llm = ChatAnthropic(model=model, api_key=api_key)
        else:
            raise ValueError(f"Unsupported provider: {provider}")
        
        logger.info(f"Judge initialized: {provider}/{model}")
    
    def evaluate_answers(
        self,
        library_name: str,
        answers: List[Dict[str, Any]],
        output_path: Optional[Path] = None,
        concurrency: int = 1,
    ) -> List[Dict[str, Any]]:
        """
        Evaluate all answers (WITH and WITHOUT docs).

        Args:
            library_name: Library name for context
            answers: List of answer dicts from Answerer
            output_path: If set, write incrementally after each evaluation
            concurrency: Number of parallel judge calls (default: 1 = sequential)

        Returns:
            List of evaluation dicts ordered by input order.
        """
        n = len(answers)
        results: Dict[int, Dict] = {}
        lock = threading.Lock()
        completed = [0]

        def _process(idx: int, answer: Dict) -> None:
            q_id = answer["question_id"]
            t0 = time.time()
            try:
                eval_result = self._evaluate_answer_pair(library_name, answer)
                elapsed = time.time() - t0
                delta = eval_result.get("delta")
                delta_str = f"delta={delta:+}" if delta is not None else "delta=n/a"
                with lock:
                    results[idx] = eval_result
                    completed[0] += 1
                    print(f"[{completed[0]}/{n}] {q_id} ✓ {delta_str} ({elapsed:.1f}s)", flush=True)
                    if output_path is not None:
                        ordered = [results[i] for i in sorted(results)]
                        self._save_incremental(ordered, output_path)
            except Exception as e:
                elapsed = time.time() - t0
                logger.exception(f"Evaluation failed for {q_id}")
                with lock:
                    results[idx] = {
                        "question_id": answer["question_id"],
                        "question_text": answer["question_text"],
                        "category": answer.get("category"),
                        "difficulty": answer.get("difficulty"),
                        "persona": answer.get("persona"),
                        "error": str(e),
                        "with_docs": None,
                        "without_docs": None,
                        "delta": None
                    }
                    completed[0] += 1
                    print(f"[{completed[0]}/{n}] {q_id} ✗ ({elapsed:.1f}s): {e}", flush=True)
                    if output_path is not None:
                        ordered = [results[i] for i in sorted(results)]
                        self._save_incremental(ordered, output_path)

        print(f"Evaluating {n} answers with judge: {self.provider}/{self.model} (concurrency={concurrency})", flush=True)

        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {pool.submit(_process, i, a): i for i, a in enumerate(answers)}
            for f in as_completed(futures):
                f.result()  # wait for completion

        evaluations = [results[i] for i in range(n)]
        valid = [e for e in evaluations if e.get("delta") is not None]
        if valid:
            avg_with = sum((e.get("with_docs") or {}).get("aggregate", 0) for e in valid) / len(valid)
            avg_without = sum((e.get("without_docs") or {}).get("aggregate", 0) for e in valid) / len(valid)
            avg_delta = sum(e["delta"] for e in valid) / len(valid)
            print("\n✓ Evaluation complete:", flush=True)
            print(f"  WITH docs avg:    {avg_with:.1f}", flush=True)
            print(f"  WITHOUT docs avg: {avg_without:.1f}", flush=True)
            print(f"  Average delta:    {avg_delta:.1f}", flush=True)
        return evaluations
    
    def _evaluate_answer_pair(
        self,
        library_name: str,
        answer: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Evaluate a single answer pair (WITH and WITHOUT)."""
        question_text = answer["question_text"]
        
        # Evaluate WITH docs
        with_docs_eval = None
        if answer.get("with_docs") and answer["with_docs"].get("answer"):
            context = self._format_context(answer["with_docs"].get("retrieved_docs", []))
            with_docs_eval = self._judge_answer(
                library_name=library_name,
                question=question_text,
                answer=answer["with_docs"]["answer"],
                context=context
            )
        
        # Evaluate WITHOUT docs
        without_docs_eval = None
        if answer.get("without_docs") and answer["without_docs"].get("answer"):
            without_docs_eval = self._judge_answer(
                library_name=library_name,
                question=question_text,
                answer=answer["without_docs"]["answer"],
                context="(No documentation provided)"
            )
        
        # Calculate delta
        delta = None
        if with_docs_eval and without_docs_eval:
            delta = with_docs_eval["aggregate"] - without_docs_eval["aggregate"]

        result = {
            "question_id": answer["question_id"],
            "question_text": question_text,
            "category": answer.get("category"),
            "difficulty": answer.get("difficulty"),
            "persona": answer.get("persona"),
            "with_docs": with_docs_eval,
            "without_docs": without_docs_eval,
            "delta": delta,
        }

        # Classify retrieval outcome (why docs helped or didn't)
        result["diagnosis"] = diagnose(answer, result)
        return result
    
    def _judge_answer(
        self,
        library_name: str,
        question: str,
        answer: str,
        context: str
    ) -> Dict[str, Any]:
        """Judge a single answer."""
        prompt = JUDGE_PROMPT.format(
            question=question,
            answer=answer,
            context=context,
            library_name=library_name
        )
        
        response = self.llm.invoke(prompt)
        raw = response.content if hasattr(response, "content") else str(response)
        
        # Parse JSON
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError("No JSON object in judge response")
        
        scores = json.loads(raw[start:end])
        
        # Validate structure
        required = {"correctness", "completeness", "specificity", "code_quality", "actionability", "aggregate"}
        if not required.issubset(scores.keys()):
            raise ValueError(f"Missing keys in judge response: {required - scores.keys()}")
        
        return scores
    
    @staticmethod
    def _format_context(docs: List[Dict[str, Any]]) -> str:
        """Format retrieved docs as context string."""
        if not docs:
            return "(No documentation retrieved)"
        
        formatted = []
        for i, doc in enumerate(docs):
            snippet = doc.get("snippet", doc.get("content", ""))
            formatted.append(f"Doc {i+1}: {snippet}")
        
        return "\n".join(formatted)
    
    def _build_evaluation_output(self, evaluations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Build the serialisable output structure for a set of evaluations."""
        return {
            "evaluated_at": self._get_timestamp(),
            "judge_model": self.model,
            "judge_provider": self.provider,
            "total_evaluations": len(evaluations),
            "evaluations": evaluations,
        }

    def _save_incremental(self, evaluations: List[Dict[str, Any]], output_path: Path) -> None:
        """Write current evaluations to disk atomically (called after each question)."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(self._build_evaluation_output(evaluations), f, indent=2)
        os.replace(tmp_path, output_path)

    def save_evaluations(
        self,
        evaluations: List[Dict[str, Any]],
        output_path: Path
    ):
        """Save evaluations to JSON file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self._build_evaluation_output(evaluations), f, indent=2)
        logger.info(f"✓ Saved evaluations for {len(evaluations)} answers to {output_path}")
    
    @staticmethod
    def load_evaluations(input_path: Path) -> Dict[str, Any]:
        """Load evaluations from JSON file."""
        with open(input_path, 'r') as f:
            return json.load(f)
    
    @staticmethod
    def _get_timestamp() -> str:
        from datetime import datetime
        return datetime.utcnow().isoformat() + "Z"
