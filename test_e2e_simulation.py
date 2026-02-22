#!/usr/bin/env python3
"""E2E test simulation for doc quality pipeline."""

import sys
import json
from pathlib import Path

sys.path.insert(0, '/workspace/doc-benchmark')

# Mock all LLM dependencies
import types
for mod_name in ['langchain_openai', 'langchain_anthropic', 'openai', 'github']:
    if mod_name not in sys.modules:
        mock_mod = types.ModuleType(mod_name)
        
        if 'langchain' in mod_name:
            class MockLLM:
                def __init__(self, **kwargs): pass
                def invoke(self, prompt):
                    # Realistic mock responses
                    if 'personas' in prompt.lower():
                        content = json.dumps({
                            "personas": [
                                {
                                    "id": "hpc_developer",
                                    "name": "HPC Developer",
                                    "description": "Expert in parallel computing",
                                    "skill_level": "advanced",
                                    "concerns": ["performance", "scalability"],
                                    "typical_questions": ["How to minimize overhead?"]
                                }
                            ]
                        })
                    elif 'question' in prompt.lower() and 'generate' in prompt.lower():
                        content = '["How to use parallel_for?", "What is task_arena?"]'
                    elif 'validation' in prompt.lower():
                        content = json.dumps({
                            "relevance": 85, "answerability": 90, "specificity": 80,
                            "aggregate": 85, "reasoning": "Good question"
                        })
                    elif 'answer' in prompt.lower() and 'documentation' in prompt.lower():
                        content = "To use parallel_for in oneTBB, write: tbb::parallel_for(0, n, [](int i) { ... });"
                    elif 'answer' in prompt.lower():
                        content = "You can parallelize loops using threading libraries."
                    elif 'correctness' in prompt.lower() or 'completeness' in prompt.lower():
                        content = json.dumps({
                            "correctness": 85, "completeness": 90, "specificity": 80,
                            "code_quality": 85, "actionability": 90, "aggregate": 86,
                            "reasoning": {"correctness": "Accurate", "completeness": "Complete",
                                        "specificity": "TBB-specific", "code_quality": "Good", 
                                        "actionability": "Clear"}
                        })
                    else:
                        content = "Mock LLM response"
                    
                    class R:
                        pass
                    R.content = content
                    return R()
            mock_mod.ChatOpenAI = MockLLM
            mock_mod.ChatAnthropic = MockLLM
        elif mod_name == 'openai':
            class MockOpenAI:
                def __init__(self, **kwargs):
                    self.embeddings = self
                def create(self, **kwargs):
                    import random
                    class Resp:
                        data = [type('obj', (), {'embedding': [random.random() for _ in range(384)]}) 
                               for _ in kwargs.get('input', [])]
                    return Resp()
            mock_mod.OpenAI = MockOpenAI
        elif mod_name == 'github':
            class MockGithub:
                def __init__(self, *args): pass
                def get_repo(self, name):
                    class Repo:
                        description = "Threading Building Blocks"
                        def get_topics(self): return ["parallel", "cpp"]
                        def get_readme(self):
                            class R:
                                decoded_content = b"# oneTBB\\nParallel programming library"
                            return R()
                        def get_issues(self, **kwargs): return []
                    return Repo()
            mock_mod.Github = MockGithub
            mock_mod.GithubException = Exception
        
        sys.modules[mod_name] = mock_mod

# Now import real modules
from doc_benchmarks.personas.analyzer import PersonaAnalyzer
from doc_benchmarks.personas.generator import PersonaGenerator
from doc_benchmarks.questions import RagasSeedExtractor, QuestionGenerator, QuestionValidator
from doc_benchmarks.eval import Answerer, Judge

print("=" * 70)
print("E2E SIMULATION: Doc Quality Pipeline for oneTBB")
print("=" * 70)

# Step 1: Personas
print("\\n[1/5] PERSONA DISCOVERY")
print("-" * 70)

analyzer = PersonaAnalyzer()
print("✓ PersonaAnalyzer initialized")

analysis = analyzer.analyze_repository("uxlfoundation/oneTBB")
print(f"✓ Analyzed repo (found {len(analysis.get('use_cases', []))} use cases)")

generator = PersonaGenerator(model="gpt-4o-mini")
personas_data = generator.generate_personas("oneTBB", analysis, target_count=5)
print(f"✓ Generated {len(personas_data['personas'])} personas")
for p in personas_data['personas']:
    print(f"  - {p['name']} ({p['skill_level']})")

# Step 2: Questions
print("\\n[2/5] QUESTION GENERATION")
print("-" * 70)

# Mock MCP client
class MockMCP:
    def get_library_docs(self, *args, **kwargs):
        return [{"content": "Mock docs about parallel_for and task_arena", "source": "mock"}]
    def resolve_library_id(self, name):
        return f"uxlfoundation/{name}"

extractor = RagasSeedExtractor(mcp_client=MockMCP())
topics = extractor.extract_topics("uxlfoundation/oneTBB", "oneTBB", max_topics=5)
print(f"✓ Extracted {len(topics)} seed topics: {topics[:3]}")

question_gen = QuestionGenerator(model="gpt-4o-mini")
questions = question_gen.generate_questions("oneTBB", personas_data['personas'], topics, questions_per_topic=2)
print(f"✓ Generated {len(questions)} questions")

# Skip validation in sandbox (requires numpy)
print(f"✓ Skipping validation (sandbox limitation)")
validated = questions[:3]  # Take first 3 for demo

# Step 3: Answers
print("\\n[3/5] ANSWER GENERATION")
print("-" * 70)

answerer = Answerer(mcp_client=MockMCP(), model="gpt-4o")
answers = answerer.generate_answers("oneTBB", "uxlfoundation/oneTBB", validated[:3], max_tokens_per_question=4000)
print(f"✓ Generated answers for {len(answers)} questions")
print(f"  - WITH docs: {sum(1 for a in answers if a.get('with_docs'))}/{len(answers)}")
print(f"  - WITHOUT docs: {sum(1 for a in answers if a.get('without_docs'))}/{len(answers)}")

# Step 4: Evaluation
print("\\n[4/5] EVALUATION (LLM-AS-JUDGE)")
print("-" * 70)

judge = Judge(model="claude-sonnet-4", provider="anthropic")
evaluations = judge.evaluate_answers("oneTBB", answers)
print(f"✓ Evaluated {len(evaluations)} answer pairs")

# Calculate stats
with_scores = [e['with_docs']['aggregate'] for e in evaluations if e.get('with_docs')]
without_scores = [e['without_docs']['aggregate'] for e in evaluations if e.get('without_docs')]
deltas = [e['delta'] for e in evaluations if e.get('delta') is not None]

if with_scores:
    print(f"  - WITH docs avg: {sum(with_scores)/len(with_scores):.1f}/100")
if without_scores:
    print(f"  - WITHOUT docs avg: {sum(without_scores)/len(without_scores):.1f}/100")
if deltas:
    print(f"  - Average delta: +{sum(deltas)/len(deltas):.1f} points")
else:
    print(f"  - Note: Some evaluations failed (mock limitations)")

# Step 5: Summary
print("\\n[5/5] SUMMARY")
print("-" * 70)
print(f"✓ Pipeline complete for oneTBB")
print(f"  Personas: {len(personas_data['personas'])}")
print(f"  Questions: {len(validated)} (validation skipped)")
print(f"  Answers: {len(answers)} pairs (WITH + WITHOUT)")
print(f"  Evaluations: {len(evaluations)}")
if deltas:
    print(f"  Documentation value: +{sum(deltas)/len(deltas):.1f} points")
else:
    print(f"  Documentation value: N/A (evaluation errors)")

print("\\n" + "=" * 70)
print("SIMULATION COMPLETE")
print("=" * 70)
print("\\nNOTE: This was a dry-run with mocked LLM responses.")
print("For real results, run with actual API keys:")
print("  export OPENAI_API_KEY=sk-...")
print("  export ANTHROPIC_API_KEY=sk-ant-...")
print("  python cli.py personas discover --product oneTBB --repo uxlfoundation/oneTBB")
