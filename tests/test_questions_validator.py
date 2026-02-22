"""Tests for QuestionValidator."""

import sys
import types
import pytest
import json
from unittest.mock import Mock, patch

# Mock modules before importing
for mod_name in ['langchain_openai', 'langchain_anthropic', 'openai']:
    if mod_name not in sys.modules:
        mock_mod = types.ModuleType(mod_name)
        if 'langchain' in mod_name:
            mock_mod.ChatOpenAI = Mock
            mock_mod.ChatAnthropic = Mock
        else:  # openai
            mock_mod.OpenAI = Mock
        sys.modules[mod_name] = mock_mod

from doc_benchmarks.questions.validator import QuestionValidator, VALIDATION_PROMPT


@pytest.fixture
def sample_questions():
    return [
        {
            "id": "q_001",
            "text": "How to use parallel_for in oneTBB?",
            "personas": ["hpc_developer"],
            "difficulty": "beginner",
            "topics": ["parallel_for"]
        },
        {
            "id": "q_002",
            "text": "What is task_arena?",
            "personas": ["cs_student"],
            "difficulty": "beginner",
            "topics": ["task_arena"]
        },
        {
            "id": "q_003",
            "text": "How do I use parallel_for?",  # Duplicate of q_001
            "personas": ["ml_engineer"],
            "difficulty": "intermediate",
            "topics": ["parallel_for"]
        }
    ]


@pytest.fixture
def mock_llm_validator():
    llm = Mock()
    resp = Mock()
    resp.content = json.dumps({
        "relevance": 85,
        "answerability": 90,
        "specificity": 80,
        "aggregate": 85,
        "reasoning": "Test"
    })
    llm.invoke.return_value = resp
    return llm


@pytest.fixture
def mock_openai_embeddings():
    client = Mock()
    resp = Mock()
    resp.data = [
        type('obj', (), {'embedding': [0.1]*384}),
        type('obj', (), {'embedding': [0.2]*384}),
        type('obj', (), {'embedding': [0.15]*384})  # Similar to first
    ]
    client.embeddings.create.return_value = resp
    return client


class TestQuestionValidatorInit:
    def test_init_defaults(self):
        with patch('doc_benchmarks.questions.validator.LANGCHAIN_AVAILABLE', True), \
             patch('doc_benchmarks.questions.validator.OPENAI_AVAILABLE', True), \
             patch('doc_benchmarks.questions.validator.ChatOpenAI', Mock(), create=True), \
             patch('doc_benchmarks.questions.validator.OpenAI', Mock(), create=True):
            val = QuestionValidator()
            assert val.threshold == 60
            assert val.similarity_threshold == 0.85
    
    def test_init_custom(self):
        with patch('doc_benchmarks.questions.validator.LANGCHAIN_AVAILABLE', True), \
             patch('doc_benchmarks.questions.validator.OPENAI_AVAILABLE', True), \
             patch('doc_benchmarks.questions.validator.ChatOpenAI', Mock(), create=True), \
             patch('doc_benchmarks.questions.validator.OpenAI', Mock(), create=True):
            val = QuestionValidator(threshold=70, similarity_threshold=0.90)
            assert val.threshold == 70
            assert val.similarity_threshold == 0.90
    
    def test_init_no_langchain(self):
        with patch('doc_benchmarks.questions.validator.LANGCHAIN_AVAILABLE', False), \
             patch('doc_benchmarks.questions.validator.OPENAI_AVAILABLE', False):
            val = QuestionValidator()
            assert val.llm is None
            assert val.openai_client is None


class TestValidateQuestion:
    def test_returns_score_dict(self, mock_llm_validator):
        mock_cls = Mock(return_value=mock_llm_validator)
        with patch('doc_benchmarks.questions.validator.ChatOpenAI', mock_cls, create=True), \
             patch('doc_benchmarks.questions.validator.LANGCHAIN_AVAILABLE', True):
            val = QuestionValidator()
            score = val._validate_question("oneTBB", "How to use parallel_for?")
            
            assert isinstance(score, dict)
            assert "relevance" in score
            assert "answerability" in score
            assert "specificity" in score
            assert "aggregate" in score
    
    def test_no_llm_returns_default_score(self):
        with patch('doc_benchmarks.questions.validator.LANGCHAIN_AVAILABLE', False):
            val = QuestionValidator()
            score = val._validate_question("oneTBB", "Test question?")
            
            assert score["aggregate"] == 100  # Default pass-through
    
    def test_invalid_json_returns_none(self, mock_llm_validator):
        mock_llm_validator.invoke.return_value.content = "Not JSON"
        mock_cls = Mock(return_value=mock_llm_validator)
        
        with patch('doc_benchmarks.questions.validator.ChatOpenAI', mock_cls, create=True), \
             patch('doc_benchmarks.questions.validator.LANGCHAIN_AVAILABLE', True):
            val = QuestionValidator()
            score = val._validate_question("oneTBB", "Test?")
            assert score is None


class TestValidateAndDedupe:
    def test_filters_low_scores(self, sample_questions, mock_llm_validator, mock_openai_embeddings):
        # First question scores high, second scores low
        responses = [
            json.dumps({"relevance": 90, "answerability": 90, "specificity": 85, "aggregate": 88, "reasoning": ""}),
            json.dumps({"relevance": 50, "answerability": 55, "specificity": 40, "aggregate": 48, "reasoning": ""}),
            json.dumps({"relevance": 85, "answerability": 85, "specificity": 80, "aggregate": 83, "reasoning": ""})
        ]
        mock_llm_validator.invoke.side_effect = [
            type('r', (), {'content': resp}) for resp in responses
        ]
        
        mock_openai_cls = Mock(return_value=mock_openai_embeddings)
        mock_llm_cls = Mock(return_value=mock_llm_validator)
        
        with patch('doc_benchmarks.questions.validator.ChatOpenAI', mock_llm_cls, create=True), \
             patch('doc_benchmarks.questions.validator.OpenAI', mock_openai_cls, create=True), \
             patch('doc_benchmarks.questions.validator.LANGCHAIN_AVAILABLE', True), \
             patch('doc_benchmarks.questions.validator.OPENAI_AVAILABLE', True):
            val = QuestionValidator(threshold=60)
            validated, stats = val.validate_and_dedupe("oneTBB", sample_questions)
            
            # Second question should be filtered out (score 48 < 60)
            assert stats["after_validation"] == 2
            assert stats["removed_low_score"] == 1
    
    def test_deduplicates_similar_questions(self, sample_questions):
        # Mock embeddings where q_001 and q_003 are similar
        mock_embeddings = Mock()
        resp = Mock()
        resp.data = [
            type('obj', (), {'embedding': [1.0] + [0.0]*383}),  # q_001
            type('obj', (), {'embedding': [0.0, 1.0] + [0.0]*382}),  # q_002 (different)
            type('obj', (), {'embedding': [0.99] + [0.0]*383})  # q_003 (very similar to q_001)
        ]
        mock_embeddings.embeddings.create.return_value = resp
        
        mock_llm = Mock()
        mock_llm.invoke.return_value.content = json.dumps({
            "relevance": 85, "answerability": 85, "specificity": 80, "aggregate": 83, "reasoning": ""
        })
        
        mock_openai_cls = Mock(return_value=mock_embeddings)
        mock_llm_cls = Mock(return_value=mock_llm)
        
        with patch('doc_benchmarks.questions.validator.ChatOpenAI', mock_llm_cls, create=True), \
             patch('doc_benchmarks.questions.validator.OpenAI', mock_openai_cls, create=True), \
             patch('doc_benchmarks.questions.validator.LANGCHAIN_AVAILABLE', True), \
             patch('doc_benchmarks.questions.validator.OPENAI_AVAILABLE', True):
            val = QuestionValidator(similarity_threshold=0.85)
            validated, stats = val.validate_and_dedupe("oneTBB", sample_questions)
            
            # Should deduplicate q_001 and q_003
            assert stats["after_deduplication"] < stats["after_validation"]
    
    def test_returns_stats(self, sample_questions, mock_llm_validator, mock_openai_embeddings):
        mock_llm_validator.invoke.return_value.content = json.dumps({
            "relevance": 85, "answerability": 85, "specificity": 80, "aggregate": 83, "reasoning": ""
        })
        
        mock_openai_cls = Mock(return_value=mock_openai_embeddings)
        mock_llm_cls = Mock(return_value=mock_llm_validator)
        
        with patch('doc_benchmarks.questions.validator.ChatOpenAI', mock_llm_cls, create=True), \
             patch('doc_benchmarks.questions.validator.OpenAI', mock_openai_cls, create=True), \
             patch('doc_benchmarks.questions.validator.LANGCHAIN_AVAILABLE', True), \
             patch('doc_benchmarks.questions.validator.OPENAI_AVAILABLE', True):
            val = QuestionValidator()
            validated, stats = val.validate_and_dedupe("oneTBB", sample_questions)
            
            assert "initial_count" in stats
            assert "after_validation" in stats
            assert "after_deduplication" in stats
            assert "removed_low_score" in stats
            assert "removed_duplicates" in stats


class TestDeduplicate:
    def test_no_openai_returns_original(self, sample_questions):
        with patch('doc_benchmarks.questions.validator.OPENAI_AVAILABLE', False):
            val = QuestionValidator()
            unique, dup_groups = val._deduplicate(sample_questions)
            
            assert len(unique) == len(sample_questions)
            assert dup_groups == []
    
    def test_merges_personas_in_duplicates(self):
        # Test that when questions are duplicated, personas are merged
        questions = [
            {"id": "q_001", "text": "Question A", "personas": ["p1"]},
            {"id": "q_002", "text": "Question A", "personas": ["p2"]}
        ]
        
        # Mock embeddings that are identical
        mock_embeddings = Mock()
        resp = Mock()
        resp.data = [
            type('obj', (), {'embedding': [1.0]*384}),
            type('obj', (), {'embedding': [1.0]*384})
        ]
        mock_embeddings.embeddings.create.return_value = resp
        
        mock_openai_cls = Mock(return_value=mock_embeddings)
        
        with patch('doc_benchmarks.questions.validator.OpenAI', mock_openai_cls, create=True), \
             patch('doc_benchmarks.questions.validator.OPENAI_AVAILABLE', True):
            val = QuestionValidator(similarity_threshold=0.99)
            unique, dup_groups = val._deduplicate(questions)
            
            # Should keep one, merge personas
            assert len(unique) == 1
            assert set(unique[0]["personas"]) == {"p1", "p2"}


class TestPromptTemplate:
    def test_has_required_placeholders(self):
        required = ["{library_name}", "{question}"]
        for placeholder in required:
            assert placeholder in VALIDATION_PROMPT
