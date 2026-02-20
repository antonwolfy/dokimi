# Implementation Plan: Intel oneAPI Docs LLM Evaluation

**Date:** 2026-02-20  
**MVP Product:** oneTBB  
**Framework:** LangChain  
**Timeline:** TBD (после согласования модулей)

---

## Phase 0: Setup & Foundation (1-2 days)

### Deliverables
- [ ] LangChain environment setup
- [ ] Context7 MCP client (credentials + test connection)
- [ ] Project structure for new modules
- [ ] Base config schema (products, MCP endpoints, LLM models)

### Modules
```
intel-docs-eval/
├── config/
│   └── products.yaml         # Product configs (repos, MCP endpoints)
├── mcp/
│   ├── base.py              # Abstract MCP client interface
│   └── context7.py          # Context7 implementation
├── personas/                # NEW: Persona discovery
│   ├── analyzer.py          # Project analysis
│   └── generator.py         # LLM-based persona proposal
├── questions/
│   ├── ragas_seed.py        # RAGAS knowledge graph
│   ├── llm_gen.py           # LLM prompt-based generation
│   └── validator.py         # Auto-validation
├── eval/
│   ├── answerer.py          # LLM answer generation (WITH/WITHOUT docs)
│   └── judge.py             # LLM-as-judge scoring
├── scraping/                # Lower priority
│   ├── github_issues.py
│   └── intel_forum.py
├── cli.py                   # Main CLI
└── requirements.txt
```

---

## Phase 1: Persona Discovery (2-3 days)

**Goal:** Given project name → propose personas automatically

### Module: `personas/analyzer.py`

**Input:** Project name (e.g., "oneTBB")

**Process:**
1. **Docs Analysis:**
   - Fetch README, getting-started guides
   - Extract use cases, examples, API patterns
   - LLM prompt: "What types of users would use this library?"

2. **Issue Analysis:**
   - Scrape GitHub issues (labels: question, help wanted)
   - Cluster common question types
   - LLM prompt: "Who asks these questions? What are their roles?"

3. **LLM Synthesis:**
   - Combine signals
   - Prompt: "Propose 5-8 user personas for oneTBB. For each: name, role, skill level (beginner/intermediate/advanced), key concerns, typical questions."

**Output:** JSON
```json
{
  "product": "oneTBB",
  "personas": [
    {
      "id": "hpc_developer",
      "name": "HPC Developer",
      "description": "High-performance computing specialist working on parallel algorithms",
      "skill_level": "advanced",
      "concerns": ["performance", "scalability", "NUMA optimization"],
      "typical_questions": ["How to minimize overhead?", "NUMA-aware scheduling?"]
    },
    ...
  ]
}
```

### Module: `personas/generator.py`

**Functionality:**
- CLI command: `python cli.py personas discover --product oneTBB --output personas/oneTBB.json`
- User reviews `oneTBB.json`
- User edits if needed (add/remove personas, adjust descriptions)
- User approves: `python cli.py personas approve --file personas/oneTBB.json`

### Acceptance Criteria
- [ ] Discovers 5-8 relevant personas for oneTBB
- [ ] JSON schema validated
- [ ] User can edit before finalizing

---

## Phase 2: Question Generation (3-4 days)

**Goal:** Generate diverse questions per persona

### Module: `questions/ragas_seed.py`

**Process:**
1. Index oneTBB docs via RAGAS
2. Build knowledge graph
3. Generate seed topics (entities, relationships, concepts)
4. Output: topic list (e.g., "task parallelism", "parallel_for", "task arena")

**Tools:** `ragas` Python library

### Module: `questions/llm_gen.py`

**Process:**
1. For each persona:
   - Load persona description + concerns
   - For each RAGAS topic:
     - LLM prompt: "You are a {persona.name}. Generate 2-3 questions about {topic} in oneTBB."
   - Mix difficulty (2 beginner + 3 intermediate + 3 advanced)
2. Output: per-persona question list

**LLM:** GPT-4o-mini or Claude Haiku (fast + cheap)

### Module: `questions/validator.py`

**Auto-validation criteria:**
1. **Relevance:** Does question mention oneTBB/APIs? (LLM check)
2. **Answerability:** Not too vague? (LLM check)
3. **Uniqueness:** Dedupe via embeddings (cosine similarity <0.85)
4. **Persona-appropriate:** Difficulty matches persona level? (LLM check)

**Threshold:** Keep only questions scoring >60/100

**Deduplication:**
- Embed all questions (text-embedding-3-small)
- Compute similarity matrix
- Merge duplicates → keep most specific version
- Tag with all applicable personas

### Output
```json
{
  "product": "oneTBB",
  "questions": [
    {
      "id": "q_001",
      "text": "How do I parallelize a for-loop with oneTBB?",
      "personas": ["hpc_developer", "ml_engineer"],
      "difficulty": "beginner",
      "topics": ["parallel_for", "task parallelism"],
      "validation_score": 85
    },
    ...
  ]
}
```

### CLI
- `python cli.py questions generate --product oneTBB --personas personas/oneTBB.json --output questions/oneTBB.json`

### Acceptance Criteria
- [ ] Generates 30-50 unique questions for oneTBB
- [ ] Questions tagged with personas
- [ ] Dedupe works (no near-duplicates)
- [ ] Validation scores included

---

## Phase 3: Answer Generation (2-3 days)

**Goal:** Get LLM answers WITH and WITHOUT docs

### Module: `eval/answerer.py`

**Scenario A: WITH docs (MCP)**
1. Load question
2. Connect to Context7 MCP
3. Retrieve relevant docs for question
4. LLM prompt: "Answer this question using the provided documentation: {question}"
5. Save answer + retrieved_docs

**Scenario B: WITHOUT docs (baseline)**
1. Load same question
2. NO MCP retrieval
3. LLM prompt: "Answer this question based on your knowledge: {question}"
4. Save answer

**LLM:** Claude Sonnet 3.5 or GPT-4o (answering LLM, separate from eval LLM)

**Output:**
```json
{
  "question_id": "q_001",
  "question_text": "How do I parallelize a for-loop with oneTBB?",
  "answers": {
    "with_docs": {
      "answer": "...",
      "retrieved_docs": ["doc1", "doc2"],
      "model": "claude-sonnet-3.5"
    },
    "without_docs": {
      "answer": "...",
      "model": "claude-sonnet-3.5"
    }
  }
}
```

### CLI
- `python cli.py answers generate --questions questions/oneTBB.json --output answers/oneTBB.json`

### Acceptance Criteria
- [ ] Context7 MCP integration works
- [ ] Both WITH/WITHOUT answers generated
- [ ] Retrieved docs captured for WITH mode

---

## Phase 4: Answer Evaluation (2-3 days)

**Goal:** Score answers on 5 dimensions (0-100 scale)

### Module: `eval/judge.py`

**LLM-as-judge:** Claude Opus or GPT-4o (DIFFERENT from answering LLM)

**Evaluation dimensions:**
1. **Correctness (0-100):** Factually accurate? (judge gets question + answer + docs)
2. **Completeness (0-100):** Full answer or missing key points?
3. **Specificity (0-100):** Intel/oneTBB-specific or generic advice?
4. **Code Quality (0-100):** If code included, is it correct/runnable?
5. **Actionability (0-100):** Can user apply immediately?

**Prompt template:**
```
You are an expert evaluator for technical documentation quality.

Question: {question}
Answer: {answer}
Retrieved Docs: {docs}

Evaluate the answer on these dimensions (0-100):
- Correctness: Is the answer factually accurate based on the docs?
- Completeness: Does it fully address the question?
- Specificity: Is it oneTBB-specific or generic?
- Code Quality: If code is present, is it correct?
- Actionability: Can the user apply this immediately?

Respond in JSON:
{
  "correctness": 85,
  "completeness": 90,
  "specificity": 75,
  "code_quality": 80,
  "actionability": 85,
  "aggregate": 83,
  "reasoning": "..."
}
```

**Aggregate score:** Mean of 5 dimensions

**Output:**
```json
{
  "question_id": "q_001",
  "evaluations": {
    "with_docs": {
      "correctness": 90,
      "completeness": 85,
      "specificity": 80,
      "code_quality": 85,
      "actionability": 90,
      "aggregate": 86
    },
    "without_docs": {
      "correctness": 70,
      "completeness": 60,
      "specificity": 50,
      "code_quality": 65,
      "actionability": 60,
      "aggregate": 61
    },
    "delta": 25
  }
}
```

### CLI
- `python cli.py eval score --answers answers/oneTBB.json --output eval/oneTBB.json`

### Acceptance Criteria
- [ ] Scores 0-100 for all 5 dimensions
- [ ] WITH vs WITHOUT comparison
- [ ] Delta (doc value) calculated

---

## Phase 5: Reporting (1-2 days)

**Goal:** Actionable JSON reports (dashboard later)

### Module: `report.py`

**Aggregations:**
1. **Per-persona scores:**
   - Average score per persona (WITH/WITHOUT)
   - Which personas benefit most from docs? (highest delta)
2. **Per-dimension breakdown:**
   - Which dimension weakest? (correctness? code quality?)
3. **Doc gaps:**
   - Questions where WITH docs score <70 → doc is missing/inadequate
4. **Hallucination risks:**
   - Questions where WITHOUT docs score high but answer is wrong

**Output:** `reports/oneTBB_report.json`

### CLI
- `python cli.py report generate --eval eval/oneTBB.json --output reports/oneTBB_report.json`

### Acceptance Criteria
- [ ] JSON report generated
- [ ] Per-persona breakdown
- [ ] Gap analysis (low-scoring questions)

---

## Phase 6: Scraping (Optional, 2-3 days)

**Lower priority — do after Phases 1-5 work**

### Module: `scraping/github_issues.py`
- Fetch issues via GitHub API
- Filter: labels (question, help wanted) + keywords
- Extract question text
- Add to question pool

### Module: `scraping/intel_forum.py`
- Web scraping (BeautifulSoup or Playwright)
- Extract threads from community.intel.com
- Filter Intel oneAPI related
- Extract question text

### CLI
- `python cli.py scrape github --repo uxlfoundation/oneTBB --output questions/scraped_github.json`
- `python cli.py scrape intel-forum --output questions/scraped_forum.json`

---

## Timeline Estimate

| Phase | Duration | Dependencies |
|-------|----------|--------------|
| 0. Setup | 1-2 days | — |
| 1. Persona Discovery | 2-3 days | Phase 0 |
| 2. Question Generation | 3-4 days | Phase 1 |
| 3. Answer Generation | 2-3 days | Phase 2 |
| 4. Evaluation | 2-3 days | Phase 3 |
| 5. Reporting | 1-2 days | Phase 4 |
| 6. Scraping (optional) | 2-3 days | — |

**Total (Phases 0-5):** 11-17 days  
**With Scraping:** 13-20 days

---

## Tech Stack

- **LangChain:** LLM orchestration, MCP clients
- **RAGAS:** Knowledge graph + seed topics
- **OpenAI / Anthropic APIs:** LLM calls
- **Context7 MCP:** Doc retrieval
- **Embeddings:** text-embedding-3-small (OpenAI)
- **Python 3.11+**

---

## Deliverables (MVP)

1. **Personas:** `personas/oneTBB.json` (5-8 auto-generated, user-approved personas)
2. **Questions:** `questions/oneTBB.json` (30-50 validated questions)
3. **Answers:** `answers/oneTBB.json` (WITH/WITHOUT docs pairs)
4. **Evaluations:** `eval/oneTBB.json` (0-100 scores, 5 dimensions)
5. **Report:** `reports/oneTBB_report.json` (aggregations, gaps, insights)

---

## Next Steps

1. **User approval** of this plan
2. Create repo: `intel-docs-eval` (separate from doc-benchmark)
3. Start Phase 0: LangChain setup + Context7 MCP client

---

_Plan ready. Awaiting go-ahead._
