"""Judge answers using LLM-as-judge approach."""

import logging
import json
from typing import List, Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

from doc_benchmarks.llm import llm_call, ChatOpenAI, ChatAnthropic, LANGCHAIN_AVAILABLE


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
        answers: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Evaluate all answers (WITH and WITHOUT docs).
        
        Args:
            library_name: Library name for context
            answers: List of answer dicts from Answerer
        
        Returns:
            List of evaluation dicts:
            [
                {
                    "question_id": "q_001",
                    "question_text": "...",
                    "with_docs": {
                        "correctness": 90,
                        "completeness": 85,
                        "specificity": 80,
                        "code_quality": 85,
                        "actionability": 90,
                        "aggregate": 86,
                        "reasoning": {...}
                    },
                    "without_docs": {
                        "correctness": 70,
                        ...
                    },
                    "delta": 16  # with_docs.aggregate - without_docs.aggregate
                }
            ]
        """
        evaluations = []
        
        for i, answer in enumerate(answers):
            logger.info(f"Evaluating {i+1}/{len(answers)}: {answer['question_id']}")
            
            try:
                eval_result = self._evaluate_answer_pair(library_name, answer)
                evaluations.append(eval_result)
            except Exception as e:
                logger.error(f"Evaluation failed for {answer['question_id']}: {e}")
                evaluations.append({
                    "question_id": answer["question_id"],
                    "question_text": answer["question_text"],
                    "error": str(e),
                    "with_docs": None,
                    "without_docs": None,
                    "delta": None
                })
        
        logger.info(f"Evaluated {len(evaluations)} answer pairs")
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
        
        return {
            "question_id": answer["question_id"],
            "question_text": question_text,
            "with_docs": with_docs_eval,
            "without_docs": without_docs_eval,
            "delta": delta
        }
    
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
    
    def save_evaluations(
        self,
        evaluations: List[Dict[str, Any]],
        output_path: Path
    ):
        """Save evaluations to JSON file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        output = {
            "evaluated_at": self._get_timestamp(),
            "judge_model": self.model,
            "judge_provider": self.provider,
            "total_evaluations": len(evaluations),
            "evaluations": evaluations
        }
        
        with open(output_path, 'w') as f:
            json.dump(output, f, indent=2)
        
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
