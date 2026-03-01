"""Tests for Judge."""

import sys
import types
import pytest
import json
from pathlib import Path
from unittest.mock import Mock, patch

# Mock langchain
for mod_name in ['langchain_openai', 'langchain_anthropic']:
    if mod_name not in sys.modules:
        mock_mod = types.ModuleType(mod_name)
        mock_mod.ChatOpenAI = Mock
        mock_mod.ChatAnthropic = Mock
        sys.modules[mod_name] = mock_mod

from doc_benchmarks.eval.judge import Judge, JUDGE_PROMPT


@pytest.fixture
def sample_answers():
    return [
        {
            "question_id": "q_001",
            "question_text": "How to use parallel_for?",
            "library_name": "oneTBB",
            "with_docs": {
                "answer": "Use tbb::parallel_for(range, lambda)...",
                "retrieved_docs": [{"snippet": "Doc about parallel_for"}],
                "model": "gpt-4o"
            },
            "without_docs": {
                "answer": "You can use parallel loops...",
                "model": "gpt-4o"
            }
        }
    ]


@pytest.fixture
def mock_judge_response():
    return json.dumps({
        "correctness": 85,
        "completeness": 90,
        "specificity": 80,
        "code_quality": 85,
        "actionability": 90,
        "aggregate": 86,
        "reasoning": {
            "correctness": "Accurate",
            "completeness": "Complete",
            "specificity": "Specific to oneTBB",
            "code_quality": "Good code",
            "actionability": "Clear steps"
        }
    })


@pytest.fixture
def mock_llm(mock_judge_response):
    llm = Mock()
    resp = Mock()
    resp.content = mock_judge_response
    llm.invoke.return_value = resp
    return llm


class TestJudgeInit:
    def test_init_openai(self):
        mock_cls = Mock()
        with patch('doc_benchmarks.eval.judge.ChatOpenAI', mock_cls, create=True), \
             patch('doc_benchmarks.eval.judge.LANGCHAIN_AVAILABLE', True):
            judge = Judge(model="gpt-4o", provider="openai")
            assert judge.model == "gpt-4o"
            assert judge.provider == "openai"
    
    def test_init_anthropic(self):
        mock_cls = Mock()
        with patch('doc_benchmarks.eval.judge.ChatAnthropic', mock_cls, create=True), \
             patch('doc_benchmarks.eval.judge.LANGCHAIN_AVAILABLE', True):
            judge = Judge(model="claude-sonnet", provider="anthropic", api_key="test")
            assert judge.model == "claude-sonnet"
            assert judge.provider == "anthropic"
    
    def test_init_unsupported_provider(self):
        mock_cls = Mock()
        with patch('doc_benchmarks.eval.judge.ChatOpenAI', mock_cls, create=True), \
             patch('doc_benchmarks.eval.judge.LANGCHAIN_AVAILABLE', True):
            with pytest.raises(ValueError) as exc:
                Judge(provider="unsupported")
            assert "Unsupported provider" in str(exc.value)
    
    def test_init_no_langchain(self):
        with patch('doc_benchmarks.eval.judge.LANGCHAIN_AVAILABLE', False):
            with pytest.raises(ImportError):
                Judge()


class TestEvaluateAnswers:
    def test_returns_list(self, sample_answers, mock_llm):
        mock_cls = Mock(return_value=mock_llm)
        with patch('doc_benchmarks.eval.judge.ChatAnthropic', mock_cls, create=True), \
             patch('doc_benchmarks.eval.judge.LANGCHAIN_AVAILABLE', True):
            judge = Judge()
            evals = judge.evaluate_answers("oneTBB", sample_answers)
            
            assert isinstance(evals, list)
            assert len(evals) == len(sample_answers)
    
    def test_includes_required_fields(self, sample_answers, mock_llm):
        mock_cls = Mock(return_value=mock_llm)
        with patch('doc_benchmarks.eval.judge.ChatAnthropic', mock_cls, create=True), \
             patch('doc_benchmarks.eval.judge.LANGCHAIN_AVAILABLE', True):
            judge = Judge()
            evals = judge.evaluate_answers("oneTBB", sample_answers)
            
            for e in evals:
                assert "question_id" in e
                assert "question_text" in e
                assert "with_docs" in e
                assert "without_docs" in e
                assert "delta" in e
    
    def test_calculates_delta(self, sample_answers, mock_llm):
        # Mock different scores for WITH and WITHOUT
        responses = [
            json.dumps({"correctness": 90, "completeness": 90, "specificity": 85, "code_quality": 90, "actionability": 90, "aggregate": 89, "reasoning": {}}),
            json.dumps({"correctness": 70, "completeness": 65, "specificity": 50, "code_quality": 60, "actionability": 65, "aggregate": 62, "reasoning": {}})
        ]
        mock_llm.invoke.side_effect = [Mock(content=r) for r in responses]
        
        mock_cls = Mock(return_value=mock_llm)
        with patch('doc_benchmarks.eval.judge.ChatAnthropic', mock_cls, create=True), \
             patch('doc_benchmarks.eval.judge.LANGCHAIN_AVAILABLE', True):
            judge = Judge()
            evals = judge.evaluate_answers("oneTBB", sample_answers)
            
            assert evals[0]["delta"] == 27  # 89 - 62
    
    def test_error_handling(self, sample_answers):
        mock_llm = Mock()
        mock_llm.invoke.side_effect = Exception("Judge error")
        mock_cls = Mock(return_value=mock_llm)
        
        with patch('doc_benchmarks.eval.judge.ChatAnthropic', mock_cls, create=True), \
             patch('doc_benchmarks.eval.judge.LANGCHAIN_AVAILABLE', True):
            judge = Judge()
            evals = judge.evaluate_answers("oneTBB", sample_answers)
            
            assert len(evals) == 1
            assert "error" in evals[0]


class TestJudgeAnswer:
    def test_parses_scores(self, mock_llm):
        mock_cls = Mock(return_value=mock_llm)
        with patch('doc_benchmarks.eval.judge.ChatAnthropic', mock_cls, create=True), \
             patch('doc_benchmarks.eval.judge.LANGCHAIN_AVAILABLE', True):
            judge = Judge()
            result = judge._judge_answer("oneTBB", "Q?", "A.", "context")
            
            assert result["correctness"] == 85
            assert result["aggregate"] == 86
            assert "reasoning" in result
    
    def test_invalid_json_raises(self, mock_llm):
        mock_llm.invoke.return_value.content = "Not JSON"
        mock_cls = Mock(return_value=mock_llm)
        
        with patch('doc_benchmarks.eval.judge.ChatAnthropic', mock_cls, create=True), \
             patch('doc_benchmarks.eval.judge.LANGCHAIN_AVAILABLE', True):
            judge = Judge()
            with pytest.raises(ValueError):
                judge._judge_answer("oneTBB", "Q?", "A.", "context")
    
    def test_missing_keys_raises(self, mock_llm):
        mock_llm.invoke.return_value.content = json.dumps({"correctness": 85})  # Missing other keys
        mock_cls = Mock(return_value=mock_llm)
        
        with patch('doc_benchmarks.eval.judge.ChatAnthropic', mock_cls, create=True), \
             patch('doc_benchmarks.eval.judge.LANGCHAIN_AVAILABLE', True):
            judge = Judge()
            with pytest.raises(ValueError) as exc:
                judge._judge_answer("oneTBB", "Q?", "A.", "context")
            assert "Missing keys" in str(exc.value)


class TestFormatContext:
    def test_empty_docs(self):
        result = Judge._format_context([])
        assert result == "(No documentation retrieved)"
    
    def test_formats_docs(self):
        docs = [
            {"snippet": "Doc 1 content"},
            {"snippet": "Doc 2 content"}
        ]
        result = Judge._format_context(docs)
        assert "Doc 1:" in result
        assert "Doc 2:" in result


class TestSaveLoadEvaluations:
    def test_save_evaluations(self, tmp_path, sample_answers, mock_llm):
        mock_cls = Mock(return_value=mock_llm)
        with patch('doc_benchmarks.eval.judge.ChatAnthropic', mock_cls, create=True), \
             patch('doc_benchmarks.eval.judge.LANGCHAIN_AVAILABLE', True):
            judge = Judge()
            evals = judge.evaluate_answers("oneTBB", sample_answers)
            
            output_path = tmp_path / "eval.json"
            judge.save_evaluations(evals, output_path)
            
            assert output_path.exists()
            data = json.loads(output_path.read_text())
            assert "evaluated_at" in data
            assert "judge_model" in data
            assert "evaluations" in data
    
    def test_load_evaluations(self, tmp_path):
        test_data = {
            "evaluated_at": "2026-02-21T00:00:00Z",
            "judge_model": "claude-sonnet",
            "evaluations": [{"question_id": "q_001"}]
        }
        
        input_path = tmp_path / "eval.json"
        input_path.write_text(json.dumps(test_data))
        
        loaded = Judge.load_evaluations(input_path)
        assert loaded["judge_model"] == "claude-sonnet"
        assert len(loaded["evaluations"]) == 1


class TestPromptTemplate:
    def test_has_placeholders(self):
        # Prompt now uses __PLACEHOLDER__ style
        required = ["__QUESTION__", "__ANSWER__", "__CONTEXT__", "__LIBRARY_NAME__"]
        for placeholder in required:
            assert placeholder in JUDGE_PROMPT
