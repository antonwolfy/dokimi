"""Generate questions using LLM based on personas and seed topics."""

import logging
import json
from typing import List, Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

from doc_benchmarks.llm import llm_call, ChatOpenAI, ChatAnthropic, LANGCHAIN_AVAILABLE


QUESTION_GENERATION_PROMPT = """You are generating technical questions for documentation quality evaluation.

**Context:**
- Library: {library_name}
- Persona: {persona_name} ({skill_level})
- Persona description: {persona_description}
- Key concerns: {concerns}
- Topic: {topic}

**Task:**
Generate {count} distinct questions that this persona would ask about this topic.

**Requirements:**
- Questions must be specific to {library_name} (not generic)
- Match the persona's skill level ({skill_level})
- Focus on the persona's concerns: {concerns}
- Be realistic (questions real users would ask)
- Include variety (how-to, troubleshooting, best practices, comparison)

**Output format:**
Respond with ONLY a JSON array of strings (no explanation):
["Question 1?", "Question 2?", ...]

Generate {count} questions now:"""


class QuestionGenerator:
    """
    Generate questions per persona and topic using LLM.
    """
    
    def __init__(
        self,
        model: str = "gpt-4o-mini",
        provider: str = "openai",
        api_key: Optional[str] = None
    ):
        """
        Args:
            model: LLM model name
            provider: "openai" or "anthropic"
            api_key: Optional API key (uses env var if not provided)
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
        
        logger.info(f"QuestionGenerator initialized: {provider}/{model}")
    
    def generate_questions(
        self,
        library_name: str,
        personas: List[Dict[str, Any]],
        topics: List[str],
        questions_per_topic: int = 2,
        difficulty_distribution: Optional[Dict[str, int]] = None
    ) -> List[Dict[str, Any]]:
        """
        Generate questions for all personas × topics.
        
        Args:
            library_name: Name of library (e.g., "oneTBB")
            personas: List of persona dicts (from personas JSON)
            topics: List of seed topics (from RagasSeedExtractor)
            questions_per_topic: Questions to generate per persona × topic
            difficulty_distribution: Target counts by difficulty level
                e.g., {"beginner": 2, "intermediate": 3, "advanced": 3}
        
        Returns:
            List of question dicts:
            [
                {
                    "id": "q_001",
                    "text": "How do I use parallel_for?",
                    "personas": ["hpc_developer"],
                    "difficulty": "beginner",
                    "topics": ["parallel_for"],
                    "metadata": {...}
                }
            ]
        """
        if difficulty_distribution is None:
            difficulty_distribution = {
                "beginner": 2,
                "intermediate": 3,
                "advanced": 3
            }
        
        all_questions = []
        question_id = 1
        
        for persona in personas:
            logger.info(
                f"Generating questions for persona: {persona['name']} "
                f"({persona['skill_level']})"
            )
            
            persona_questions = self._generate_for_persona(
                library_name=library_name,
                persona=persona,
                topics=topics,
                questions_per_topic=questions_per_topic,
                difficulty_distribution=difficulty_distribution
            )
            
            # Assign IDs and add to collection
            for q in persona_questions:
                q["id"] = f"q_{question_id:03d}"
                question_id += 1
                all_questions.append(q)
        
        logger.info(f"Generated {len(all_questions)} total questions")
        return all_questions
    
    def _generate_for_persona(
        self,
        library_name: str,
        persona: Dict[str, Any],
        topics: List[str],
        questions_per_topic: int,
        difficulty_distribution: Dict[str, int]
    ) -> List[Dict[str, Any]]:
        """Generate questions for a single persona across topics."""
        persona_questions = []
        
        # Sample topics (don't need all topics for every persona)
        import random
        target_total = sum(difficulty_distribution.values())
        topics_to_use = random.sample(topics, min(len(topics), target_total // questions_per_topic))
        
        for topic in topics_to_use:
            try:
                questions_text = self._call_llm(
                    library_name=library_name,
                    persona=persona,
                    topic=topic,
                    count=questions_per_topic
                )
                
                for text in questions_text:
                    persona_questions.append({
                        "text": text,
                        "personas": [persona["id"]],
                        "difficulty": persona["skill_level"],  # Inherit from persona
                        "topics": [topic],
                        "metadata": {
                            "generated_for_persona": persona["name"],
                            "model": self.model,
                            "provider": self.provider
                        }
                    })
                    
            except Exception as e:
                logger.error(
                    f"Failed to generate questions for {persona['name']} × {topic}: {e}"
                )
                continue
        
        return persona_questions
    
    def _call_llm(
        self,
        library_name: str,
        persona: Dict[str, Any],
        topic: str,
        count: int
    ) -> List[str]:
        """Call LLM to generate questions."""
        prompt = QUESTION_GENERATION_PROMPT.format(
            library_name=library_name,
            persona_name=persona["name"],
            skill_level=persona["skill_level"],
            persona_description=persona.get("description", ""),
            concerns=", ".join(persona.get("concerns", [])),
            topic=topic,
            count=count
        )
        
        response = self.llm.invoke(prompt)
        raw = response.content if hasattr(response, "content") else str(response)
        
        # Parse JSON array
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start == -1 or end == 0:
            raise ValueError("No JSON array in LLM response")
        
        questions = json.loads(raw[start:end])
        if not isinstance(questions, list):
            raise ValueError("LLM did not return a list")
        
        # Clean
        return [str(q).strip() for q in questions if q]
    
    def save_questions(self, questions: List[Dict[str, Any]], output_path: Path):
        """Save questions to JSON file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        output = {
            "generated_at": self._get_timestamp(),
            "model": self.model,
            "provider": self.provider,
            "total_questions": len(questions),
            "questions": questions
        }
        
        with open(output_path, 'w') as f:
            json.dump(output, f, indent=2)
        
        logger.info(f"✓ Saved {len(questions)} questions to {output_path}")
    
    @staticmethod
    def _get_timestamp() -> str:
        from datetime import datetime
        return datetime.utcnow().isoformat() + "Z"
