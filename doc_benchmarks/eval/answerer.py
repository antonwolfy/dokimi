"""Generate answers to questions using LLM (with and without documentation)."""

import logging
import json
from typing import List, Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from langchain_openai import ChatOpenAI
    from langchain_anthropic import ChatAnthropic
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False

from .reranker import SimpleReranker


ANSWER_PROMPT_WITH_DOCS = """You are a technical documentation expert answering a user question.

**Question:** {question}

**Relevant documentation:**
{docs}

**Task:**
Answer the question using ONLY the provided documentation above. Be specific, accurate, and actionable. Include code examples if relevant.

**Answer:**"""


ANSWER_PROMPT_WITHOUT_DOCS = """You are a technical expert answering a user question based on your knowledge.

**Question:** {question}

**Task:**
Answer the question based on your training knowledge. Be specific and include code examples if relevant.

**Answer:**"""


class Answerer:
    """
    Generate answers to questions using LLM.
    
    Supports two modes:
    - WITH docs: Retrieve docs via MCP, then answer with context
    - WITHOUT docs: Answer from LLM knowledge only (baseline)
    """
    
    def __init__(
        self,
        mcp_client=None,
        model: str = "gpt-4o",
        provider: str = "openai",
        api_key: Optional[str] = None,
        top_k: int = 5,
        rerank_threshold: float = 0.3,
        debug_retrieval: bool = False
    ):
        """
        Args:
            mcp_client: MCP client for doc retrieval (e.g., Context7Client)
            model: LLM model name
            provider: "openai" or "anthropic"
            api_key: Optional API key
            top_k: Number of docs to retrieve before reranking
            rerank_threshold: Minimum relevance score (0-1) to keep docs
            debug_retrieval: If True, include detailed retrieval metadata in output
        """
        if not LANGCHAIN_AVAILABLE:
            raise ImportError(
                "langchain not available. "
                "Install: pip install langchain-openai langchain-anthropic"
            )
        
        self.mcp_client = mcp_client
        self.model = model
        self.provider = provider
        self.top_k = top_k
        self.debug_retrieval = debug_retrieval
        
        # Initialize reranker
        self.reranker = SimpleReranker(threshold=rerank_threshold)
        logger.info(f"Reranker initialized with threshold={rerank_threshold:.2f}")
        
        # If api_key not provided, check environment
        if not api_key:
            import os
            if provider == "openai":
                api_key = os.getenv("OPENAI_API_KEY")
            elif provider == "anthropic":
                api_key = os.getenv("ANTHROPIC_API_KEY")
        
        # Check for OpenRouter API key (starts with sk-or-)
        openrouter_base = None
        if api_key and api_key.startswith("sk-or-"):
            openrouter_base = "https://openrouter.ai/api/v1"
            logger.info("Detected OpenRouter API key, using openrouter.ai endpoint")
        
        if provider == "openai":
            if api_key:
                self.llm = ChatOpenAI(
                    model=model, 
                    api_key=api_key,
                    base_url=openrouter_base
                )
            else:
                self.llm = ChatOpenAI(model=model)
        elif provider == "anthropic":
            if api_key:
                self.llm = ChatAnthropic(model=model, api_key=api_key)
            else:
                self.llm = ChatAnthropic(model=model)
        else:
            raise ValueError(f"Unsupported provider: {provider}")
        
        logger.info(f"Answerer initialized: {provider}/{model}, MCP={'yes' if mcp_client else 'no'}")
    
    def generate_answers(
        self,
        library_name: str,
        library_id: str,
        questions: List[Dict[str, Any]],
        max_tokens_per_question: int = 4000
    ) -> List[Dict[str, Any]]:
        """
        Generate answers for all questions (WITH and WITHOUT docs).
        
        Args:
            library_name: Library name (e.g., "oneTBB")
            library_id: Library ID for MCP (e.g., "uxlfoundation/oneTBB")
            questions: List of question dicts from QuestionGenerator
            max_tokens_per_question: Max tokens to retrieve per question
        
        Returns:
            List of answer dicts:
            [
                {
                    "question_id": "q_001",
                    "question_text": "...",
                    "library_name": "oneTBB",
                    "with_docs": {
                        "answer": "...",
                        "retrieved_docs": [...],
                        "model": "gpt-4o",
                        "doc_source": "context7"
                    },
                    "without_docs": {
                        "answer": "...",
                        "model": "gpt-4o"
                    }
                }
            ]
        """
        answers = []
        
        for i, q in enumerate(questions):
            logger.info(f"Generating answers for question {i+1}/{len(questions)}: {q['id']}")
            
            try:
                answer_pair = self._generate_answer_pair(
                    library_name=library_name,
                    library_id=library_id,
                    question=q,
                    max_tokens=max_tokens_per_question
                )
                answers.append(answer_pair)
                
            except Exception as e:
                logger.error(f"Failed to generate answers for {q['id']}: {e}")
                # Add placeholder with error
                answers.append({
                    "question_id": q["id"],
                    "question_text": q["text"],
                    "library_name": library_name,
                    "error": str(e),
                    "with_docs": None,
                    "without_docs": None
                })
        
        logger.info(f"Generated answers for {len(answers)} questions")
        return answers
    
    def _generate_answer_pair(
        self,
        library_name: str,
        library_id: str,
        question: Dict[str, Any],
        max_tokens: int
    ) -> Dict[str, Any]:
        """Generate WITH and WITHOUT answers for a single question."""
        question_text = question["text"]
        
        # WITH docs
        with_docs_answer = None
        if self.mcp_client is not None:
            retrieved_docs, retrieval_metadata = self._retrieve_docs(
                library_id, question_text, max_tokens
            )
            
            if retrieved_docs:
                # Generate answer with retrieved docs
                with_docs_answer = self._generate_with_docs(
                    question_text, retrieved_docs, retrieval_metadata
                )
            else:
                # Fallback: no relevant docs found
                logger.warning(
                    f"No relevant docs for {question['id']}, "
                    f"metadata: {retrieval_metadata}"
                )
                with_docs_answer = {
                    "answer": "[FALLBACK: No relevant documentation found]",
                    "retrieved_docs": [],
                    "model": self.model,
                    "doc_source": "fallback_none",
                    "retrieval_metadata": retrieval_metadata if self.debug_retrieval else None
                }
        else:
            logger.warning(f"No MCP client - skipping WITH docs for {question['id']}")
        
        # WITHOUT docs
        without_docs_answer = self._generate_without_docs(question_text)
        
        return {
            "question_id": question["id"],
            "question_text": question_text,
            "library_name": library_name,
            "with_docs": with_docs_answer,
            "without_docs": without_docs_answer
        }
    
    def _retrieve_docs(
        self,
        library_id: str,
        question: str,
        max_tokens: int
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Retrieve relevant docs via MCP client with reranking.
        
        Returns:
            (docs, metadata): Reranked docs and retrieval metadata dict
        """
        metadata = {
            "raw_count": 0,
            "after_rerank": 0,
            "top_score": None,
            "avg_score": None,
            "fallback_triggered": False
        }
        
        try:
            # Retrieve top-k docs
            # Note: Context7 client returns single doc, so we call it once for now
            # TODO: Update Context7 client to support top_k natively
            raw_docs = self.mcp_client.get_library_docs(
                library_id=library_id,
                query=question,
                max_tokens=max_tokens
            )
            metadata["raw_count"] = len(raw_docs)
            logger.info(f"Retrieved {len(raw_docs)} raw doc chunks")
            
            if not raw_docs:
                return [], metadata
            
            # Rerank docs by relevance
            reranked_docs = self.reranker.rerank(question, raw_docs)
            metadata["after_rerank"] = len(reranked_docs)
            
            if reranked_docs:
                scores = [d.get('relevance_score', 0) for d in reranked_docs]
                metadata["top_score"] = round(max(scores), 3)
                metadata["avg_score"] = round(sum(scores) / len(scores), 3)
                
                # Keep top 3 after reranking
                return reranked_docs[:3], metadata
            else:
                # No docs passed threshold
                metadata["fallback_triggered"] = True
                logger.warning(f"No docs passed rerank threshold for question")
                return [], metadata
                
        except Exception as e:
            logger.error(f"Doc retrieval failed: {e}")
            return [], metadata
    
    def _generate_with_docs(
        self,
        question: str,
        docs: List[Dict[str, Any]],
        retrieval_metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Generate answer WITH documentation context."""
        if not docs:
            return {
                "answer": "[No documentation retrieved]",
                "retrieved_docs": [],
                "model": self.model,
                "doc_source": "none",
                "retrieval_metadata": retrieval_metadata if self.debug_retrieval else None
            }
        
        # Format docs
        docs_text = "\n\n---\n\n".join(d["content"] for d in docs)
        
        # Generate answer
        prompt = ANSWER_PROMPT_WITH_DOCS.format(
            question=question,
            docs=docs_text[:15000]  # Limit to avoid token overflow
        )
        
        response = self.llm.invoke(prompt)
        answer_text = response.content if hasattr(response, "content") else str(response)
        
        result = {
            "answer": answer_text,
            "retrieved_docs": [
                {
                    "source": d.get("source", "unknown"),
                    "snippet": d["content"][:200] + "..." if len(d["content"]) > 200 else d["content"],
                    "relevance_score": d.get("relevance_score")
                }
                for d in docs
            ],
            "model": self.model,
            "doc_source": docs[0].get("source", "unknown") if docs else "none"
        }
        
        # Add metadata if debug mode enabled
        if self.debug_retrieval and retrieval_metadata:
            result["retrieval_metadata"] = retrieval_metadata
        
        return result
    
    def _generate_without_docs(self, question: str) -> Dict[str, Any]:
        """Generate answer WITHOUT documentation (baseline)."""
        prompt = ANSWER_PROMPT_WITHOUT_DOCS.format(question=question)
        
        response = self.llm.invoke(prompt)
        answer_text = response.content if hasattr(response, "content") else str(response)
        
        return {
            "answer": answer_text,
            "model": self.model
        }
    
    def save_answers(
        self,
        answers: List[Dict[str, Any]],
        output_path: Path
    ):
        """Save answers to JSON file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        output = {
            "generated_at": self._get_timestamp(),
            "model": self.model,
            "provider": self.provider,
            "total_questions": len(answers),
            "answers": answers
        }
        
        with open(output_path, 'w') as f:
            json.dump(output, f, indent=2)
        
        logger.info(f"✓ Saved answers for {len(answers)} questions to {output_path}")
    
    @staticmethod
    def load_answers(input_path: Path) -> Dict[str, Any]:
        """Load answers from JSON file."""
        with open(input_path, 'r') as f:
            return json.load(f)
    
    @staticmethod
    def _get_timestamp() -> str:
        from datetime import datetime
        return datetime.utcnow().isoformat() + "Z"
