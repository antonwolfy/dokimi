# Unified Implementation Plan: doc-benchmark + LLM Evaluation

**Date:** 2026-02-20  
**Repo:** napetrov/doc-benchmark (one repo, extended)  
**MVP Product:** oneTBB  
**Framework:** LangChain  

---

## Context

Существующий `doc-benchmark` решает **структурные метрики** (coverage, freshness, readability, examples).  
Новая задача — добавить **LLM evaluation pipeline**: как хорошо docs помогают отвечать на реальные вопросы.

Всё остаётся в одном репо. Новые модули добавляются в `doc_benchmarks/` по тому же принципу.

---

## New Directory Structure

```
doc-benchmark/
├── doc_benchmarks/
│   ├── ingest/          # ✅ Existing: loader, chunker
│   ├── metrics/         # ✅ Existing: coverage, freshness, readability, examples
│   ├── runner/          # ✅ Existing: run, compare
│   ├── report/          # ✅ Existing: json_report, markdown_report
│   ├── gate/            # ✅ Existing: soft, hard, regression, bands
│   │
│   ├── personas/        # 🆕 Phase 1: Auto-discover personas
│   │   ├── __init__.py
│   │   ├── analyzer.py      # GitHub + docs analysis
│   │   └── generator.py     # LLM persona proposal
│   │
│   ├── questions/       # 🆕 Phase 2: Question generation
│   │   ├── __init__.py
│   │   ├── ragas_seed.py    # RAGAS knowledge graph topics
│   │   ├── llm_gen.py       # LLM prompt-based generation
│   │   └── validator.py     # Auto-validation + dedupe
│   │
│   ├── eval/            # 🆕 Phase 3-4: Answer generation + scoring
│   │   ├── __init__.py
│   │   ├── answerer.py      # LLM answers WITH/WITHOUT docs
│   │   └── judge.py         # LLM-as-judge scoring (0-100, 5 dims)
│   │
│   └── mcp/             # 🆕 Phase 0: MCP clients
│       ├── __init__.py
│       ├── base.py          # Abstract MCP interface
│       └── context7.py      # Context7 implementation
│
├── personas/            # Data: generated persona JSONs
├── questions/           # Data: question sets (existing + new)
├── answers/             # Data: LLM answer pairs (WITH/WITHOUT)
├── eval/                # Data: scoring results
├── reports/             # Data: ✅ existing + new eval reports
│
├── cli.py               # ✅ Existing CLI + new subcommands
├── requirements.txt     # Extended with LangChain, RAGAS
└── .github/workflows/   # ✅ Existing CI (unchanged)
```

---

## Phase 0: Setup & Foundation (1-2 days)

**Goal:** Подготовить окружение и MCP client для Context7.

### Tasks
- [ ] Расширить `requirements.txt`: langchain, langchain-openai, ragas, openai, httpx
- [ ] Создать `doc_benchmarks/mcp/base.py` — абстрактный интерфейс MCP
- [ ] Создать `doc_benchmarks/mcp/context7.py` — Context7 HTTP client
- [ ] Добавить `config/products.yaml` — конфиги продуктов (oneTBB: repo, context7_id, etc.)
- [ ] Проверить Context7 API (endpoint, auth, `resolve-library-id`, `get-library-docs`)

### Context7 API (Known)
```
POST https://mcp.context7.com/mcp
Tools:
  - resolve-library-id: name → /org/repo
  - get-library-docs: library_id + topic → docs
```

### Deliverables
- Working Context7 client: `ctx7 = Context7Client(); docs = ctx7.get_docs("oneTBB", "parallel_for")`
- Config file with oneTBB product definition

---

## Phase 1: Persona Discovery (2-3 days)

**Goal:** Дать имя продукта → получить список релевантных персон.

### Flow
```
"oneTBB" 
  → GitHub API: README + issues (label:question)
  → LLM: "Analyze these docs/issues. Propose 5-8 user personas."
  → personas/oneTBB.json
  → User reviews/edits
  → CLI: python cli.py personas approve --file personas/oneTBB.json
```

### `doc_benchmarks/personas/analyzer.py`
- GitHub API: fetch README, getting-started, issues
- Extract signals: use cases, API names, question patterns
- Output: raw context for LLM

### `doc_benchmarks/personas/generator.py`
- LLM prompt → structured JSON personas
- Schema: `{id, name, description, skill_level, concerns[], typical_questions[]}`

### CLI Commands
```bash
python cli.py personas discover --product oneTBB
python cli.py personas approve --file personas/oneTBB.json
```

### Output: `personas/oneTBB.json`
```json
{
  "product": "oneTBB",
  "personas": [
    {
      "id": "hpc_developer",
      "name": "HPC Developer",
      "skill_level": "advanced",
      "concerns": ["performance", "scalability", "NUMA"],
      "typical_questions": ["How to minimize task overhead?"]
    }
  ]
}
```

---

## Phase 2: Question Generation (3-4 days)

**Goal:** Для каждой персоны — набор разнообразных вопросов. Без дублей.

### Flow
```
personas/oneTBB.json
  → RAGAS: index oneTBB docs → seed topics
  → LLM: per-persona × per-topic → questions
  → Validator: relevance + answerability + dedupe
  → questions/oneTBB.json
```

### `doc_benchmarks/questions/ragas_seed.py`
- Fetch oneTBB docs via Context7
- RAGAS knowledge graph → list of topics/concepts
- Output: `["parallel_for", "task_arena", "flow_graph", "tbb::blocked_range", ...]`

### `doc_benchmarks/questions/llm_gen.py`
- For each persona × each topic:
  - Prompt: *"You are {persona}. Generate 2 questions about {topic} in oneTBB. Mix difficulty: beginner/intermediate/advanced."*
- Output: raw question list

### `doc_benchmarks/questions/validator.py`
- **Relevance check:** LLM score 0-100, threshold >60
- **Answerability:** not too vague
- **Dedupe:** embed all questions (text-embedding-3-small), cosine >0.85 = duplicate
- Keep most specific, tag with all applicable personas

### CLI
```bash
python cli.py questions generate \
  --product oneTBB \
  --personas personas/oneTBB.json \
  --output questions/oneTBB.json
```

### Output: `questions/oneTBB.json`
```json
{
  "product": "oneTBB",
  "generated_at": "2026-02-20",
  "questions": [
    {
      "id": "q_001",
      "text": "How do I parallelize a for-loop with oneTBB?",
      "personas": ["hpc_developer", "ml_engineer"],
      "difficulty": "beginner",
      "topics": ["parallel_for"],
      "validation_score": 85
    }
  ]
}
```

### Target
- 30-50 unique questions для oneTBB MVP

---

## Phase 3: Answer Generation (2-3 days)

**Goal:** Для каждого вопроса — два ответа: с доками (Context7) и без.

### Flow
```
questions/oneTBB.json
  → Scenario A: Context7 MCP → retrieve docs → LLM answer
  → Scenario B: no docs → LLM answer (baseline)
  → answers/oneTBB.json
```

### `doc_benchmarks/eval/answerer.py`
- **WITH docs:** вопрос → Context7 → релевантные chunks → LLM с контекстом
- **WITHOUT docs:** вопрос → LLM без контекста
- Один и тот же LLM для обоих (configurable, default: gpt-4o или claude-sonnet)

### CLI
```bash
python cli.py answers generate \
  --questions questions/oneTBB.json \
  --output answers/oneTBB.json
```

### Output: `answers/oneTBB.json`
```json
{
  "question_id": "q_001",
  "question_text": "How do I parallelize a for-loop with oneTBB?",
  "with_docs": {
    "answer": "Use tbb::parallel_for...",
    "retrieved_docs": ["doc_chunk_1", "doc_chunk_2"],
    "model": "gpt-4o"
  },
  "without_docs": {
    "answer": "You can use OpenMP or TBB...",
    "model": "gpt-4o"
  }
}
```

---

## Phase 4: Evaluation / Scoring (2-3 days)

**Goal:** Оценить ответы по 5 измерениям (0-100). LLM-as-judge.

### `doc_benchmarks/eval/judge.py`
- **Judge LLM:** отдельная модель от answerer (configurable, default: claude-sonnet)
- **Input:** question + answer + retrieved_docs (для WITH)
- **5 dimensions:**
  1. **Correctness** — фактически верно?
  2. **Completeness** — полный ответ?
  3. **Specificity** — oneTBB-specific или generic?
  4. **Code Quality** — если есть код, он рабочий?
  5. **Actionability** — пользователь может применить сразу?

- **Aggregate:** среднее по 5 измерениям
- **Delta:** with_docs.aggregate − without_docs.aggregate

### CLI
```bash
python cli.py eval score \
  --answers answers/oneTBB.json \
  --output eval/oneTBB.json
```

### Output: `eval/oneTBB.json`
```json
{
  "question_id": "q_001",
  "with_docs": {
    "correctness": 90, "completeness": 85, "specificity": 80,
    "code_quality": 85, "actionability": 90, "aggregate": 86
  },
  "without_docs": {
    "correctness": 65, "completeness": 60, "specificity": 40,
    "code_quality": 60, "actionability": 55, "aggregate": 56
  },
  "delta": 30,
  "doc_gap": "Missing examples for nested parallelism",
  "hallucination_note": "Without docs, model confused parallel_for with OpenMP syntax"
}
```

---

## Phase 5: Reporting (1-2 days)

**Goal:** JSON отчёт с агрегацией, выявление gaps.

### `doc_benchmarks/report/llm_eval_report.py`
Агрегации:
1. **Per-persona scores** (WITH vs WITHOUT, delta per persona)
2. **Per-dimension breakdown** (что слабее всего?)
3. **Doc gaps** (questions где with_docs < 70 → docs недостаточно)
4. **Hallucination risks** (without_docs высокий но wrong)
5. **Top/bottom questions** (лучшие и худшие по delta)

### CLI
```bash
python cli.py report llm-eval \
  --eval eval/oneTBB.json \
  --personas personas/oneTBB.json \
  --output reports/oneTBB_llm_eval.json
```

### Output snippet
```json
{
  "product": "oneTBB",
  "summary": {
    "avg_with_docs": 82,
    "avg_without_docs": 58,
    "avg_delta": 24
  },
  "by_persona": {
    "hpc_developer": {"with_docs": 88, "without_docs": 65, "delta": 23},
    "cs_student":    {"with_docs": 75, "without_docs": 45, "delta": 30}
  },
  "by_dimension": {
    "correctness": {"with": 88, "without": 62},
    "specificity":  {"with": 80, "without": 35}
  },
  "doc_gaps": [
    {"question_id": "q_017", "score": 58, "gap": "No docs on NUMA-aware task arenas"},
    {"question_id": "q_023", "score": 61, "gap": "Flow graph examples missing"}
  ]
}
```

---

## Phase 6: Scraping (Optional, after MVP)

**Lower priority — только после работающего Phases 0-5**

### Modules
- `doc_benchmarks/scraping/github_issues.py` — GitHub API, filter by labels + keywords
- `doc_benchmarks/scraping/intel_forum.py` — web scraping (BeautifulSoup/Playwright)

### CLI
```bash
python cli.py scrape github --repo uxlfoundation/oneTBB --output questions/scraped_github.json
python cli.py scrape intel-forum --product oneTBB --output questions/scraped_forum.json
```

---

## Updated CLI Subcommands

| Existing | New |
|----------|-----|
| `run` | `personas discover` |
| `compare` | `personas approve` |
| `report` | `questions generate` |
| | `answers generate` |
| | `eval score` |
| | `report llm-eval` |
| | `scrape github` |
| | `scrape intel-forum` |

---

## Tech Stack (additions)

| Library | Use |
|---------|-----|
| `langchain` | LLM orchestration, chains |
| `langchain-openai` | OpenAI integration |
| `langchain-anthropic` | Anthropic integration |
| `ragas` | Knowledge graph + seed topics |
| `openai` | Embeddings (text-embedding-3-small) |
| `httpx` | Context7 MCP HTTP client |
| `PyGithub` | GitHub API for persona/scraping |
| `beautifulsoup4` | Intel Forum scraping (Phase 6) |

---

## Timeline

| Phase | Задача | Дней |
|-------|--------|------|
| 0 | Setup + MCP client | 1-2 |
| 1 | Persona discovery | 2-3 |
| 2 | Question generation | 3-4 |
| 3 | Answer generation | 2-3 |
| 4 | Evaluation/scoring | 2-3 |
| 5 | Reporting | 1-2 |
| 6 | Scraping (optional) | 2-3 |
| **Total (0-5)** | | **11-17** |

---

## MVP Deliverables

| Файл | Описание |
|------|----------|
| `personas/oneTBB.json` | 5-8 auto-generated персон |
| `questions/oneTBB.json` | 30-50 validated вопросов |
| `answers/oneTBB.json` | WITH/WITHOUT пары ответов |
| `eval/oneTBB.json` | Scores по 5 dimensions |
| `reports/oneTBB_llm_eval.json` | Финальный report с gaps |

---

## Next Step

**Phase 0 — начинаем немедленно:**
1. Обновить `requirements.txt`
2. Создать `doc_benchmarks/mcp/` с Context7 client
3. Создать `config/products.yaml`
4. Протестировать Context7 API call для oneTBB

_Готов начать. Нужен API ключ для Context7 (или он open access)?_
