"""Tests for Answerer."""

import sys
import types
import pytest
import json
from pathlib import Path
from unittest.mock import Mock, patch

# Mock langchain modules
for mod_name in ['langchain_openai', 'langchain_anthropic']:
    if mod_name not in sys.modules:
        mock_mod = types.ModuleType(mod_name)
        mock_mod.ChatOpenAI = Mock
        mock_mod.ChatAnthropic = Mock
        sys.modules[mod_name] = mock_mod

from doc_benchmarks.eval.answerer import Answerer, ANSWER_PROMPT_WITH_DOCS, ANSWER_PROMPT_WITHOUT_DOCS


@pytest.fixture
def sample_questions():
    return [
        {
            "id": "q_001",
            "text": "How to use parallel_for in oneTBB?",
            "personas": ["hpc_developer"],
            "topics": ["parallel_for"]
        },
        {
            "id": "q_002",
            "text": "What is task_arena?",
            "personas": ["cs_student"],
            "topics": ["task_arena"]
        }
    ]


@pytest.fixture
def mock_mcp_client():
    client = Mock()
    client.get_library_docs.return_value = [
        {
            "content": "parallel_for documentation: Use tbb::parallel_for(range, lambda) to parallelize loops.",
            "source": "context7",
            "library_id": "uxlfoundation/oneTBB"
        }
    ]
    return client


@pytest.fixture
def mock_llm():
    llm = Mock()
    resp = Mock()
    resp.content = "This is a test answer from LLM."
    llm.invoke.return_value = resp
    return llm


class TestAnswererInit:
    def test_init_openai(self):
        mock_cls = Mock()
        with patch('doc_benchmarks.eval.answerer.ChatOpenAI', mock_cls, create=True), \
             patch('doc_benchmarks.eval.answerer.LANGCHAIN_AVAILABLE', True):
            answerer = Answerer(model="gpt-4o", provider="openai")
            assert answerer.model == "gpt-4o"
            assert answerer.provider == "openai"
            mock_cls.assert_called_once()
    
    def test_init_anthropic(self):
        mock_cls = Mock()
        with patch('doc_benchmarks.eval.answerer.ChatAnthropic', mock_cls, create=True), \
             patch('doc_benchmarks.eval.answerer.LANGCHAIN_AVAILABLE', True):
            answerer = Answerer(model="claude-opus", provider="anthropic", api_key="test")
            assert answerer.model == "claude-opus"
            assert answerer.provider == "anthropic"
    
    def test_init_unsupported_provider(self):
        mock_cls = Mock()
        with patch('doc_benchmarks.eval.answerer.ChatOpenAI', mock_cls, create=True), \
             patch('doc_benchmarks.eval.answerer.LANGCHAIN_AVAILABLE', True):
            with pytest.raises(ValueError) as exc:
                Answerer(provider="unsupported")
            assert "Unsupported provider" in str(exc.value)
    
    def test_init_no_langchain(self):
        with patch('doc_benchmarks.eval.answerer.LANGCHAIN_AVAILABLE', False):
            with pytest.raises(ImportError) as exc:
                Answerer()
            assert "LLM dependencies not available" in str(exc.value)


class TestGenerateAnswers:
    def test_returns_list(self, sample_questions, mock_mcp_client, mock_llm):
        mock_cls = Mock(return_value=mock_llm)
        with patch('doc_benchmarks.eval.answerer.ChatOpenAI', mock_cls, create=True), \
             patch('doc_benchmarks.eval.answerer.LANGCHAIN_AVAILABLE', True):
            answerer = Answerer(mcp_client=mock_mcp_client)
            answers = answerer.generate_answers("oneTBB", "uxlfoundation/oneTBB", sample_questions)
            
            assert isinstance(answers, list)
            assert len(answers) == len(sample_questions)
    
    def test_includes_both_modes(self, sample_questions, mock_mcp_client, mock_llm):
        mock_cls = Mock(return_value=mock_llm)
        with patch('doc_benchmarks.eval.answerer.ChatOpenAI', mock_cls, create=True), \
             patch('doc_benchmarks.eval.answerer.LANGCHAIN_AVAILABLE', True):
            answerer = Answerer(mcp_client=mock_mcp_client)
            answers = answerer.generate_answers("oneTBB", "uxlfoundation/oneTBB", sample_questions)
            
            for ans in answers:
                assert "with_docs" in ans
                assert "without_docs" in ans
                assert "question_id" in ans
                assert "question_text" in ans
    
    def test_no_mcp_client_skips_with_docs(self, sample_questions, mock_llm):
        mock_cls = Mock(return_value=mock_llm)
        with patch('doc_benchmarks.eval.answerer.ChatOpenAI', mock_cls, create=True), \
             patch('doc_benchmarks.eval.answerer.LANGCHAIN_AVAILABLE', True):
            answerer = Answerer()  # No MCP client
            answers = answerer.generate_answers("oneTBB", "uxlfoundation/oneTBB", sample_questions)
            
            assert answers[0]["with_docs"] is None
            assert answers[0]["without_docs"] is not None
    
    def test_error_handling(self, sample_questions, mock_mcp_client):
        mock_llm = Mock()
        mock_llm.invoke.side_effect = Exception("LLM error")
        mock_cls = Mock(return_value=mock_llm)
        
        with patch('doc_benchmarks.eval.answerer.ChatOpenAI', mock_cls, create=True), \
             patch('doc_benchmarks.eval.answerer.LANGCHAIN_AVAILABLE', True):
            answerer = Answerer(mcp_client=mock_mcp_client)
            answers = answerer.generate_answers("oneTBB", "uxlfoundation/oneTBB", sample_questions)
            
            # Should not crash, should include error field
            assert len(answers) == len(sample_questions)
            assert "error" in answers[0]


class TestRetrieveDocs:
    def test_calls_mcp_client(self, mock_mcp_client):
        mock_llm = Mock()
        mock_cls = Mock(return_value=mock_llm)
        
        with patch('doc_benchmarks.eval.answerer.ChatOpenAI', mock_cls, create=True), \
             patch('doc_benchmarks.eval.answerer.LANGCHAIN_AVAILABLE', True):
            answerer = Answerer(mcp_client=mock_mcp_client)
            docs = answerer._retrieve_docs("uxlfoundation/oneTBB", "parallel_for", 4000)
            
            mock_mcp_client.get_library_docs.assert_called_once()
            assert len(docs) > 0
    
    def test_error_handling(self, mock_mcp_client):
        mock_mcp_client.get_library_docs.side_effect = Exception("Network error")
        mock_llm = Mock()
        mock_cls = Mock(return_value=mock_llm)
        
        with patch('doc_benchmarks.eval.answerer.ChatOpenAI', mock_cls, create=True), \
             patch('doc_benchmarks.eval.answerer.LANGCHAIN_AVAILABLE', True):
            answerer = Answerer(mcp_client=mock_mcp_client)
            docs = answerer._retrieve_docs("uxlfoundation/oneTBB", "test question", 4000)
            
            assert docs == []


class TestGenerateWithDocs:
    def test_with_docs(self, mock_llm):
        mock_cls = Mock(return_value=mock_llm)
        docs = [{"content": "Test doc content", "source": "context7"}]
        
        with patch('doc_benchmarks.eval.answerer.ChatOpenAI', mock_cls, create=True), \
             patch('doc_benchmarks.eval.answerer.LANGCHAIN_AVAILABLE', True):
            answerer = Answerer()
            result = answerer._generate_with_docs("Test question?", docs)
            
            assert "answer" in result
            assert "retrieved_docs" in result
            assert "model" in result
            assert result["doc_source"] == "context7"
    
    def test_empty_docs(self, mock_llm):
        mock_cls = Mock(return_value=mock_llm)
        
        with patch('doc_benchmarks.eval.answerer.ChatOpenAI', mock_cls, create=True), \
             patch('doc_benchmarks.eval.answerer.LANGCHAIN_AVAILABLE', True):
            answerer = Answerer()
            result = answerer._generate_with_docs("Test question?", [])
            
            assert result["answer"] == "[No documentation retrieved]"
            assert result["retrieved_docs"] == []


class TestGenerateWithoutDocs:
    def test_generates_answer(self, mock_llm):
        mock_cls = Mock(return_value=mock_llm)
        
        with patch('doc_benchmarks.eval.answerer.ChatOpenAI', mock_cls, create=True), \
             patch('doc_benchmarks.eval.answerer.LANGCHAIN_AVAILABLE', True):
            answerer = Answerer()
            result = answerer._generate_without_docs("Test question?")
            
            assert "answer" in result
            assert "model" in result
            assert result["answer"] == "This is a test answer from LLM."


class TestSaveLoadAnswers:
    def test_save_answers(self, tmp_path, sample_questions, mock_mcp_client, mock_llm):
        mock_cls = Mock(return_value=mock_llm)
        
        with patch('doc_benchmarks.eval.answerer.ChatOpenAI', mock_cls, create=True), \
             patch('doc_benchmarks.eval.answerer.LANGCHAIN_AVAILABLE', True):
            answerer = Answerer(mcp_client=mock_mcp_client)
            answers = answerer.generate_answers("oneTBB", "uxlfoundation/oneTBB", sample_questions[:1])
            
            output_path = tmp_path / "answers.json"
            answerer.save_answers(answers, output_path)
            
            assert output_path.exists()
            data = json.loads(output_path.read_text())
            assert "generated_at" in data
            assert "model" in data
            assert "answers" in data
            assert data["total_questions"] == 1
    
    def test_load_answers(self, tmp_path):
        test_data = {
            "generated_at": "2026-02-21T00:00:00Z",
            "model": "gpt-4o",
            "total_questions": 1,
            "answers": [{"question_id": "q_001", "question_text": "Test?"}]
        }
        
        input_path = tmp_path / "answers.json"
        input_path.write_text(json.dumps(test_data))
        
        loaded = Answerer.load_answers(input_path)
        assert loaded["model"] == "gpt-4o"
        assert len(loaded["answers"]) == 1


class TestPromptTemplates:
    def test_with_docs_template(self):
        assert "{question}" in ANSWER_PROMPT_WITH_DOCS
        assert "{docs}" in ANSWER_PROMPT_WITH_DOCS
    
    def test_without_docs_template(self):
        assert "{question}" in ANSWER_PROMPT_WITHOUT_DOCS
