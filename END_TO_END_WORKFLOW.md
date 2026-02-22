# End-to-End Workflow: Doc Quality Evaluation Pipeline

**Date:** 2026-02-21  
**Status:** Phase 4 implementation complete

---

## Pipeline Overview

```
GitHub Repo
    ↓
1. Persona Discovery → personas/oneTBB.json
    ↓
2. Topic Extraction → (auto via Context7)
    ↓
3. Question Generation → questions/oneTBB.json
    ↓
4. Answer Generation → answers/oneTBB.json
    (WITH docs via Context7 + WITHOUT docs baseline)
    ↓
5. LLM-as-Judge Evaluation → eval/oneTBB.json
    (5 dimensions: correctness, completeness, specificity, code_quality, actionability)
    ↓
6. Report Generation → reports/oneTBB_eval.json
    (aggregations, gaps, hallucinations)
```

---

## Step-by-Step Usage

### Prerequisites

```bash
# Install dependencies
pip install -r requirements.txt

# Set API keys
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export GITHUB_TOKEN="ghp_..."  # Optional, for higher rate limits
```

### Step 1: Discover Personas

```bash
python cli.py personas discover \
  --product oneTBB \
  --repo uxlfoundation/oneTBB \
  --count 5 \
  --save-analysis

# Output: personas/oneTBB.json
# Contains: 5-8 user personas with skill levels, concerns, typical questions
```

**Review & Edit:**
```bash
cat personas/oneTBB.json
# Edit if needed: add/remove/adjust personas
```

**Approve:**
```bash
python cli.py personas approve --file personas/oneTBB.json
```

---

### Step 2: Generate Questions

```bash
python cli.py questions generate \
  --product oneTBB \
  --personas personas/oneTBB.json \
  --count 2 \
  --validate

# What happens:
# 1. Extracts seed topics via Context7 (cached)
# 2. Generates questions per persona × topic
# 3. Validates (LLM scoring, threshold 60)
# 4. Deduplicates (embedding similarity > 0.85)
# 5. Merges personas for duplicates

# Output: questions/oneTBB.json (30-50 unique questions)
```

**Review Questions:**
```bash
cat questions/oneTBB.json | jq '.questions[] | {id, text, personas}'
```

---

### Step 3: Generate Answers

```bash
python cli.py answers generate \
  --product oneTBB \
  --questions questions/oneTBB.json \
  --model gpt-4o \
  --max-tokens 4000

# What happens:
# 1. For each question:
#    a. WITH docs: Context7 retrieves docs → LLM answers with context
#    b. WITHOUT docs: LLM answers from knowledge only
# 2. Saves both answers per question

# Output: answers/oneTBB.json
# Each entry has: with_docs {answer, retrieved_docs} + without_docs {answer}
```

**Review Answers:**
```bash
cat answers/oneTBB.json | jq '.answers[0]'
# Check:
# - with_docs.answer vs without_docs.answer
# - retrieved_docs snippets
```

---

### Step 4: Evaluate Answers

```bash
python cli.py eval score \
  --product oneTBB \
  --answers answers/oneTBB.json \
  --judge-model claude-sonnet-4 \
  --judge-provider anthropic

# What happens:
# 1. LLM-as-judge (separate from answerer model)
# 2. Scores each answer on 5 dimensions (0-100):
#    - Correctness
#    - Completeness
#    - Specificity
#    - Code Quality
#    - Actionability
# 3. Calculates aggregate (average of 5)
# 4. Calculates delta (WITH - WITHOUT)

# Output: eval/oneTBB.json
```

**Review Scores:**
```bash
cat eval/oneTBB.json | jq '.evaluations[] | {id: .question_id, with: .with_docs.aggregate, without: .without_docs.aggregate, delta}'

# Statistics:
cat eval/oneTBB.json | jq '.evaluations | map(.delta) | add / length'
# Average delta = how much docs improve answers
```

---

### Step 5: Generate Report (Phase 5 - TBD)

```bash
# TODO: Phase 5 implementation
python cli.py report llm-eval \
  --eval eval/oneTBB.json \
  --personas personas/oneTBB.json \
  --output reports/oneTBB_eval.json

# Will aggregate:
# - Per-persona scores
# - Per-dimension breakdown
# - Doc gaps (where WITH < 70)
# - Hallucination risks (WHERE WITHOUT high but wrong)
```

---

## Example Output Structure

### personas/oneTBB.json
```json
{
  "product": "oneTBB",
  "personas": [
    {
      "id": "hpc_developer",
      "name": "HPC Developer",
      "skill_level": "advanced",
      "concerns": ["performance", "scalability"],
      "typical_questions": ["How to minimize overhead?"]
    }
  ]
}
```

### questions/oneTBB.json
```json
{
  "total_questions": 35,
  "questions": [
    {
      "id": "q_001",
      "text": "How to use parallel_for in oneTBB?",
      "personas": ["hpc_developer", "ml_engineer"],
      "difficulty": "intermediate",
      "topics": ["parallel_for"],
      "validation_score": 85
    }
  ]
}
```

### answers/oneTBB.json
```json
{
  "total_questions": 35,
  "answers": [
    {
      "question_id": "q_001",
      "question_text": "How to use parallel_for?",
      "with_docs": {
        "answer": "Use tbb::parallel_for(range, lambda) { ... }",
        "retrieved_docs": [{"snippet": "parallel_for docs..."}],
        "model": "gpt-4o",
        "doc_source": "context7"
      },
      "without_docs": {
        "answer": "You can parallelize loops with OpenMP or TBB...",
        "model": "gpt-4o"
      }
    }
  ]
}
```

### eval/oneTBB.json
```json
{
  "total_evaluations": 35,
  "evaluations": [
    {
      "question_id": "q_001",
      "with_docs": {
        "correctness": 90,
        "completeness": 85,
        "specificity": 88,
        "code_quality": 90,
        "actionability": 92,
        "aggregate": 89
      },
      "without_docs": {
        "correctness": 70,
        "completeness": 65,
        "specificity": 45,
        "code_quality": 60,
        "actionability": 65,
        "aggregate": 61
      },
      "delta": 28
    }
  ]
}
```

---

## Key Metrics

**Average Scores (example):**
- WITH docs: 82/100
- WITHOUT docs: 58/100
- **Delta: +24 points** ← Documentation value!

**Per-dimension insights:**
- Specificity gap largest (+35) → docs make answers oneTBB-specific
- Correctness gap (+20) → docs reduce hallucinations
- Code quality gap (+15) → docs provide correct examples

**Doc gaps** (WHERE WITH < 70):
- "NUMA-aware task arenas" → only 58/100 even WITH docs
- "Flow graph error handling" → 62/100

**Hallucination risks** (WHERE WITHOUT high but WRONG):
- "parallel_reduce syntax" → 75/100 WITHOUT but uses wrong API

---

## Timeline

**Full pipeline** (oneTBB example):
1. Personas: 2 min (GitHub analysis + LLM)
2. Questions: 5 min (topic extraction + generation + validation for 35 questions)
3. Answers: 10 min (70 LLM calls: 35 WITH + 35 WITHOUT)
4. Evaluation: 10 min (70 judge calls: 35 WITH + 35 WITHOUT)
5. **Total: ~30 minutes for 35 questions**

**Cost estimate** (OpenAI + Anthropic):
- Questions: $0.50 (gpt-4o-mini)
- Answers: $5 (gpt-4o, 70 calls)
- Eval: $7 (claude-sonnet-4, 70 calls)
- **Total: ~$12.50 for full evaluation**

---

## Next Steps

- **Phase 5:** Report generation (aggregations, visualizations)
- **Phase 6 (optional):** Scraping real user questions (GitHub issues, Intel Forum)

---

**Status:** Phase 0-4 complete, ready for acceptance testing on real oneTBB data.
