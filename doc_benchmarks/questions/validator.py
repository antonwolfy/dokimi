"""Validate and deduplicate generated questions."""

import logging
import json
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    from langchain_openai import ChatOpenAI
    from langchain_anthropic import ChatAnthropic
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False


VALIDATION_PROMPT = """You are validating a technical question for documentation quality evaluation.

**Library:** {library_name}
**Question:** {question}

**Validation criteria:**
1. **Relevance (0-100):** Does the question mention {library_name} or its APIs/concepts?
2. **Answerability (0-100):** Is the question clear and answerable (not too vague)?
3. **Specificity (0-100):** Is it specific to {library_name} (not generic programming)?

Respond with ONLY a JSON object (no explanation):
{{
  "relevance": 85,
  "answerability": 90,
  "specificity": 80,
  "aggregate": 85,
  "reasoning": "Brief explanation"
}}

Aggregate score is the average of the three dimensions."""


class QuestionValidator:
    """
    Validate questions for relevance/answerability and deduplicate.
    """
    
    def __init__(
        self,
        llm_model: str = "gpt-4o-mini",
        llm_provider: str = "openai",
        embedding_model: str = "text-embedding-3-small",
        threshold: int = 60,
        similarity_threshold: float = 0.85,
        api_key: Optional[str] = None
    ):
        """
        Args:
            llm_model: Model for validation (LLM-as-judge)
            llm_provider: "openai" or "anthropic"
            embedding_model: Model for embeddings (dedupe)
            threshold: Min aggregate score to keep (0-100)
            similarity_threshold: Cosine similarity for deduplication (0.0-1.0)
            api_key: Optional API key
        """
        self.llm_model = llm_model
        self.llm_provider = llm_provider
        self.embedding_model = embedding_model
        self.threshold = threshold
        self.similarity_threshold = similarity_threshold
        
        # Init LLM for validation
        if LANGCHAIN_AVAILABLE:
            if llm_provider == "openai":
                self.llm = ChatOpenAI(model=llm_model, api_key=api_key)
            elif llm_provider == "anthropic":
                self.llm = ChatAnthropic(model=llm_model, api_key=api_key)
            else:
                raise ValueError(f"Unsupported LLM provider: {llm_provider}")
        else:
            self.llm = None
            logger.warning("LangChain not available — validation disabled")
        
        # Init OpenAI client for embeddings
        if OPENAI_AVAILABLE:
            self.openai_client = OpenAI(api_key=api_key)
        else:
            self.openai_client = None
            logger.warning("OpenAI not available — deduplication disabled")
        
        logger.info(f"QuestionValidator initialized: threshold={threshold}, similarity={similarity_threshold}")
    
    def validate_and_dedupe(
        self,
        library_name: str,
        questions: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Validate questions and remove duplicates.
        
        Args:
            library_name: Library name for validation context
            questions: List of question dicts from QuestionGenerator
        
        Returns:
            (validated_questions, stats)
            - validated_questions: Filtered and deduplicated list
            - stats: Dict with counts and removed questions
        """
        logger.info(f"Validating {len(questions)} questions...")
        
        # Step 1: Validate each question (LLM scoring)
        validated = []
        for q in questions:
            score = self._validate_question(library_name, q["text"])
            if score is not None:
                q["validation_score"] = score["aggregate"]
                q["validation_details"] = score
                if score["aggregate"] >= self.threshold:
                    validated.append(q)
        
        logger.info(f"After validation: {len(validated)}/{len(questions)} passed (threshold={self.threshold})")
        
        # Step 2: Deduplicate (embedding similarity)
        deduplicated, dup_groups = self._deduplicate(validated)
        
        logger.info(f"After deduplication: {len(deduplicated)}/{len(validated)} unique")
        
        stats = {
            "initial_count": len(questions),
            "after_validation": len(validated),
            "after_deduplication": len(deduplicated),
            "removed_low_score": len(questions) - len(validated),
            "removed_duplicates": len(validated) - len(deduplicated),
            "duplicate_groups": dup_groups
        }
        
        return deduplicated, stats
    
    def _validate_question(self, library_name: str, question_text: str) -> Optional[Dict[str, Any]]:
        """Validate a single question using LLM."""
        if self.llm is None:
            # No validation available — pass through
            return {
                "relevance": 100,
                "answerability": 100,
                "specificity": 100,
                "aggregate": 100,
                "reasoning": "Validation disabled (no LLM)"
            }
        
        try:
            prompt = VALIDATION_PROMPT.format(
                library_name=library_name,
                question=question_text
            )
            
            response = self.llm.invoke(prompt)
            raw = response.content if hasattr(response, "content") else str(response)
            
            # Parse JSON
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start == -1 or end == 0:
                raise ValueError("No JSON object in response")
            
            score = json.loads(raw[start:end])
            
            # Validate structure
            required = {"relevance", "answerability", "specificity", "aggregate"}
            if not required.issubset(score.keys()):
                raise ValueError(f"Missing keys in validation response: {required - score.keys()}")
            
            return score
            
        except Exception as e:
            logger.error(f"Validation failed for question: {question_text[:50]}... — {e}")
            return None
    
    def _deduplicate(
        self, questions: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[List[str]]]:
        """
        Deduplicate questions using embedding similarity.
        
        Returns:
            (unique_questions, duplicate_groups)
        """
        if self.openai_client is None:
            logger.warning("Deduplication skipped (OpenAI not available)")
            return questions, []
        
        if len(questions) == 0:
            return [], []
        
        # Compute embeddings
        texts = [q["text"] for q in questions]
        embeddings = self._get_embeddings(texts)
        
        # Build similarity matrix and find duplicates
        import numpy as np
        
        embeddings_array = np.array(embeddings)
        # Normalize
        norms = np.linalg.norm(embeddings_array, axis=1, keepdims=True)
        embeddings_norm = embeddings_array / norms
        
        # Cosine similarity matrix
        similarity = embeddings_norm @ embeddings_norm.T
        
        # Find duplicate groups (similarity > threshold)
        unique_indices = []
        duplicate_groups = []
        persona_merge_map = {}  # best_idx -> list of all similar indices
        seen = set()
        
        for i in range(len(questions)):
            if i in seen:
                continue
            
            # Find all questions similar to i (including i itself)
            similar = [j for j in range(i, len(questions))
                      if similarity[i, j] > self.similarity_threshold and j not in seen]
            
            if len(similar) > 1:
                # Duplicate group found
                duplicate_groups.append([questions[j]["text"] for j in similar])
                # Keep the most specific (longest text as heuristic)
                best_idx = max(similar, key=lambda j: len(questions[j]["text"]))
                unique_indices.append(best_idx)
                persona_merge_map[best_idx] = similar  # Save for merging later
                seen.update(similar)
            else:
                unique_indices.append(i)
                seen.add(i)
        
        # Build unique questions list
        unique_questions = [questions[i] for i in sorted(unique_indices)]
        
        # Merge persona lists for kept questions from duplicate groups
        for kept_idx, similar_indices in persona_merge_map.items():
            kept_q = questions[kept_idx]
            # Merge personas from all duplicates
            all_personas = set(kept_q.get("personas", []))
            for j in similar_indices:
                all_personas.update(questions[j].get("personas", []))
            
            # Update in unique_questions
            for q in unique_questions:
                if q.get("id") == kept_q.get("id") or q.get("text") == kept_q.get("text"):
                    q["personas"] = list(all_personas)
                    break
        
        return unique_questions, duplicate_groups
    
    def _get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Get embeddings from OpenAI."""
        try:
            response = self.openai_client.embeddings.create(
                input=texts,
                model=self.embedding_model
            )
            return [item.embedding for item in response.data]
        except Exception as e:
            logger.error(f"Embedding request failed: {e}")
            raise
