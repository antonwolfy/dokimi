# Задача: Evaluation Intel oneAPI Documentation Quality

**Дата:** 2026-02-20  
**Проекты:** oneDAL, oneTBB, oneMKL, oneDNN, scikit-learn-intelex, Intel Distribution for Python, optimization-zone

---

## Цель

Оценить качество документации Intel oneAPI продуктов по тому, **насколько она отвечает на вопросы разных пользователей и кейсов**.

---

## Сценарии оценки

### 1. Оценка документации напрямую
**Что:** Анализ самих markdown/HTML файлов документации без LLM  
**Метрики:**
- Структура (headings, code blocks, completeness)
- Freshness (актуальность)
- Readability (сложность текста)
- Runnable examples (работают ли примеры)

**Статус:** ✅ Частично реализовано (текущий doc-benchmark: 4 метрики)

---

### 2. Оценка ответов агента С MCP сервером
**Что:** LLM отвечает на вопросы С подключенной документацией через MCP  
**MCP варианты:**
- Context7 (уже индексирует oneAPI repos)
- Другие MCP-серверы (custom?)

**Процесс:**
1. Вопрос задаётся LLM
2. MCP server retrieves relevant docs
3. LLM генерит ответ WITH context
4. Оценка ответа (correctness, completeness, specificity, code quality, actionability)

**Статус:** ❓ Не реализовано (было в original vision, но не в MVP)

---

### 3. Оценка ответов агента БЕЗ MCP (baseline)
**Что:** LLM отвечает на вопросы БЕЗ документации (pure LLM knowledge)  
**Зачем:** Baseline для сравнения — насколько docs улучшают ответы

**Процесс:**
1. Тот же вопрос задаётся LLM
2. MCP отключен (no retrieval)
3. LLM генерит ответ WITHOUT context
4. Оценка ответа (same dimensions)
5. **Compare:** WITH docs vs. WITHOUT docs → delta = doc value

**Статус:** ❓ Не реализовано

---

## Источники вопросов

### a. Статичные вопросы (вручную заданные)
**Что:** Заранее подготовленный набор вопросов  
**Примеры:**
- "How do I parallelize a for-loop with oneTBB?"
- "What's the difference between oneDNN and MKL-DNN?"
- "How to install oneDAL on Ubuntu?"

**Статус:** ❓ Нужно создать вручную или взять из существующих источников

---

### b. Автогенерация вопросов

#### b.1. Генерация для разных персон/профайлов
**Персоны (из original plan):**
- ML Engineer (PyTorch/TF integration, training optimization)
- HPC Developer (parallel algorithms, NUMA, vectorization)
- CS Student (getting started, installation, basic concepts)
- DevOps/CI Engineer (install, config, Docker, CI/CD)
- Migration Engineer (CUDA→oneAPI, OpenMP→TBB)
- AI Coding Agent (API refs, code snippets, best practices)
- Troubleshooter (error messages, debugging, performance)
- Framework Integrator (using Intel libs inside PyTorch/TF/JAX)

**Распределение сложности (из original plan):**
- 2 Beginner + 3 Intermediate + 3 Advanced = 8 вопросов на персону
- 8 персон × 8 вопросов = 64 вопроса на продукт

#### b.2. Как должна происходить генерация вопросов?
**❓ ВОПРОС 1:** Какой подход предпочтителен?
- **RAGAS-based:** knowledge graphs из docs → synthetic questions (diverse: simple, reasoning, multi-hop)
- **LLM prompt-based:** "Generate 8 questions for ML Engineer persona about oneTBB"
- **Template-based:** "How to {task} with {library}?" заполнение слотов
- **Hybrid:** комбинация подходов

**❓ ВОПРОС 2:** Нужна ли валидация сгенерированных вопросов?
- Human review (ручная проверка)?
- Auto-filtering (relevance check)?
- Accept as-is?

**Статус:** ❓ Не реализовано, метод не определён

---

### c. Скан вопросов из релевантных источников (автоматизация)

#### c.1. Issues проекта
**Что:** Парсить GitHub issues из oneAPI repos  
**Примеры:**
- https://github.com/uxlfoundation/oneTBB/issues
- https://github.com/uxlfoundation/oneDNN/issues
- https://github.com/oneapi-src/oneDAL/issues

**Процесс:**
1. Fetch issues via GitHub API
2. Filter: questions (not bugs/feature requests)
3. Extract question text
4. Deduplicate + categorize

**❓ ВОПРОС 3:** Как фильтровать вопросы от bugs?
- По labels (`question`, `help wanted`)?
- По keywords в title/body?
- LLM classification?

#### c.2. Поиск по Intel форуму
**Что:** Intel Developer Zone, Intel Community Forum  
**URLs:**
- https://community.intel.com/
- Specific forums: oneAPI, HPC, AI

**Процесс:**
1. Scrape forum threads (web scraping or API if available)
2. Extract Q&A pairs
3. Filter Intel oneAPI related

**❓ ВОПРОС 4:** Есть ли API у Intel Forum или только scraping?

#### c.3. Поиск вопросов из внешних источников
**Что:** StackOverflow, Reddit, other tech forums  
**Примеры:**
- StackOverflow tags: `onetbb`, `onednn`, `mkl`, `intel-oneapi`
- Reddit: r/IntelOneAPI, r/HPC

**Процесс:**
1. API queries (StackExchange API for SO)
2. Filter by tags/keywords
3. Extract question text

**❓ ВОПРОС 5:** Периодичность обновления вопросов?
- One-time scrape?
- Daily/weekly updates?
- Event-triggered (new release)?

---

## Архитектура (draft)

```
┌─────────────────────────────────────────────────────┐
│            Question Generation & Collection          │
│                                                      │
│  ┌────────────┐  ┌─────────────┐  ┌──────────────┐ │
│  │ Static Q's │  │ Auto-gen    │  │ Scraped Q's  │ │
│  │ (manual)   │  │ (personas)  │  │ (GH/forum/SO)│ │
│  └─────┬──────┘  └──────┬──────┘  └──────┬───────┘ │
│        └─────────────┬──┴────────────────┘         │
└──────────────────────┼─────────────────────────────┘
                       │
        ┌──────────────┴──────────────┐
        ▼                             ▼
┌────────────────┐          ┌────────────────┐
│ LLM WITH docs  │          │ LLM W/O docs   │
│ (MCP: Context7)│          │ (baseline)     │
└───────┬────────┘          └───────┬────────┘
        │                           │
        ▼                           ▼
┌─────────────────────────────────────────┐
│         Multi-Dim Scoring               │
│  • correctness                          │
│  • completeness                         │
│  • specificity (Intel-specific)         │
│  • code quality                         │
│  • actionability                        │
└─────────────────┬───────────────────────┘
                  ▼
┌──────────────────────────────────────────┐
│         Gap Reports                       │
│  • Score breakdown per product           │
│  • Per-persona weak spots                │
│  • Doc gaps by category                  │
│  • Hallucination risks                   │
│  • Actionable fix list                   │
└──────────────────────────────────────────┘
```

---

## Метрики оценки ответов (LLM eval)

**Dimensions (from original plan):**
1. **Correctness:** Фактическая правильность
2. **Completeness:** Полнота ответа
3. **Specificity:** Intel-specific details (не generic advice)
4. **Code quality:** Если код в ответе — работает ли, best practices
5. **Actionability:** Можно ли сразу применить

**Оценщик:** Separate LLM (Claude) → eliminates self-evaluation bias

**❓ ВОПРОС 6:** Какой scoring scale?
- Binary (pass/fail)?
- 1-5 scale?
- 0.0-1.0 continuous?

---

## Связь с текущим doc-benchmark

**Что уже есть:**
- Metrics 1-4 (coverage, freshness, readability, examples) → **Scenario 1** (прямая оценка docs)
- CLI + CI + reports

**Что нужно добавить:**
- **Scenario 2 & 3:** LLM evaluation (WITH/WITHOUT docs)
- **Question generation:** personas + auto-gen
- **Question scraping:** GitHub issues, forums, SO
- **Multi-dim scoring:** correctness, completeness, specificity, code quality, actionability
- **Gap reports:** per-product, per-persona

**Gap:** Текущий tool НЕ решает задачу eval ответов агента — только структурные метрики docs.

---

## Уточняющие вопросы

### Генерация вопросов
1. **Метод генерации:** RAGAS / LLM prompt / templates / hybrid?
2. **Валидация:** Human review / auto-filter / accept as-is?

### Скрейпинг вопросов
3. **Фильтр issues:** По labels / keywords / LLM classification?
4. **Intel Forum API:** Есть или только scraping?
5. **Периодичность:** One-time / daily / event-triggered?

### Оценка ответов
6. **Scoring scale:** Binary / 1-5 / 0.0-1.0?
7. **LLM для оценки:** Claude / GPT / other? (отдельный от answering LLM)
8. **Ground truth:** Нужны ли "правильные" ответы для сравнения или reference-free?

### MCP integration
9. **Context7 access:** Уже есть API keys / credentials?
10. **Другие MCP servers:** Нужны ли кроме Context7? (custom Intel docs MCP?)

### Scope
11. **Приоритет продуктов:** Все 7 сразу или начать с 1-2 (oneTBB, oneDNN)?
12. **Количество вопросов per product:** 64 (8 personas × 8 Q) достаточно или больше?
13. **Deliverable format:** Dashboard / JSON reports / Jira tickets?

---

## Следующий шаг

**Ждём ответы на вопросы** → потом составлю детальный план implementation.

