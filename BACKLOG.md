# BACKLOG

## Active

---

### #48 — Next oneTBB executable tasks: reduce, scan, flow graph
**Scope:** Task generation / executable benchmarks
**Status:** READY

Add the next three oneTBB terminal-bench-style tasks to cover core APIs that are not yet exercised by the current ParRes-inspired suite.

Tasks:
- `onetbb-parallel-reduce` — compute aggregate values over generated data with `oneapi::tbb::parallel_reduce`; verifier should compare against a serial reference and check source usage.
- `onetbb-parallel-scan` — implement prefix sums with `oneapi::tbb::parallel_scan`; verifier should validate exact prefix output/signature against serial reference.
- `onetbb-flow-graph` — build a small producer/transform/consumer graph with `oneapi::tbb::flow::graph`; verifier should validate deterministic output and graph API usage.

Deliverables:
- Docker environment, starter source, instruction, oracle `solution/solve.sh`, pytest verifier, `task.toml` for each task
- Offline oracle verification in CI with `--network none`
- README task table updates and coverage matrix entries
- Keep task sizes small enough for reliable CI, but strong enough to reject keyword-only or no-op solutions

---

### #49 — Repository structure and documentation cleanup
**Scope:** Repository hygiene / documentation
**Status:** READY

Prune and organize repository docs so the project is easier to navigate as it now includes both static docs-quality benchmarking and executable terminal-bench tasks.

Deliverables:
- Update top-level README to reflect current state after oneTBB task additions
- Split or link detailed docs into a small `docs/` structure where useful, instead of overloading README
- Add/refresh a contributor flow for adding terminal-bench tasks
- Add a oneTBB task coverage matrix: API/concept, task name, verifier type, difficulty, status
- Reconcile stale files (`STATUS*.md`, `NEXT_STEPS.md`, `BACKLOG.md`) so they do not contradict the current `main`
- Make Docker image naming and task metadata conventions explicit

---

### #47 — oneTBB executable task suite from ParRes Kernels
**Scope:** Task generation / executable benchmarks
**Status:** COMPLETED

Use https://github.com/ParRes/Kernels as a seed corpus for oneTBB tasks. The repo already contains simple Parallel Research Kernels with TBB implementations, which makes it a good base for terminal-bench style tasks that validate both documentation understanding and working oneTBB code.

Completed in PR #49:
- `onetbb-nstream` — memory bandwidth / parallel loop update
- `onetbb-stencil` — 2D neighborhood computation and boundary handling
- `onetbb-transpose` — blocked parallel transpose
- ParRes/Kernels provenance notes
- CI oracle verification for all included oneTBB tasks

Remaining ideas moved into future task candidates:
- `sparse` — sparse matrix-vector style workload
- `p2p` — point-to-point style communication pattern adapted to shared memory

---

- [x] PR #29 — Multi-evaluator (LLM Judge Panel)
**Scope:** Evaluation quality
**Status:** PLANNED

Вместо одного судьи — панель из N LLM-судей с разными профилями/ролями.
- Каждый судья даёт независимую оценку
- Итоговый скор = средневзвешенное
- Метрика inter-rater agreement (насколько судьи сходятся / расходятся)
- Расхождение = сигнал качества вопроса или документации

---

### #30 — HTML Dashboard
**Scope:** Reporting
**Status:** PLANNED

Статический HTML-файл (Chart.js встроен) поверх существующего dashboard.json.
- Bar chart по продуктам
- Sortable/filterable таблица
- Drill-down по клику на продукт
- Генерируется той же командой `dashboard generate --format html`
- Jenkins может публиковать как артефакт

---

### #31 — Jenkins / CI Pipeline
**Scope:** Automation
**Status:** PLANNED

Jenkinsfile для автоматического прогона benchmark.
- Параметризованный запуск: выбор библиотек, модели
- `benchmark batch --all` → `dashboard generate` → commit DASHBOARD.md
- Уведомление в Slack/Teams при деградации скора

---

### #32 — Real benchmark run: oneTBB + Dashboard validation
**Scope:** Validation
**Status:** PLANNED

Первый реальный прогон нового пайплайна end-to-end:
- `benchmark run --library onetbb`
- Проверить что dashboard собирается из реальных данных
- Зафиксировать baseline, сравнить с предыдущим (Feb 25)

---

## Completed

- [x] PR #29 — Multi-evaluator LLM Judge Panel (3 roles, weighted aggregate, agreement score) (merged Feb 27, 2026)
- [x] PR #28 — Dashboard generate (DASHBOARD.md + JSON) (merged Feb 27, 2026)
- [x] PR #27 — Library registry (22 продукта) + benchmark run/batch (merged Feb 27, 2026)
- [x] PR #26 — Question quality analysis (merged Feb 27, 2026)
- [x] PR #25 — Arbitrary products (no GitHub repo required) + --context7-id (merged Feb 27, 2026)
- [x] PR #24 — Failure Analysis / diagnose (merged Feb 26, 2026)
- [x] PR #23 — CodeRabbit followup fixes for PR #22 (merged Feb 26, 2026)
- [x] PR #22 — Multiple Documentation Sources (merged Feb 26, 2026)
- [x] PR #21 — CodeRabbit followup fixes (merged Feb 26, 2026)
- [x] PR #20 — Retry с backoff + baseline save/list/compare (merged Feb 26, 2026)
- [x] PR #19 — Параллельные API-вызовы / ThreadPoolExecutor (merged Feb 26, 2026)
- [x] PR #18 — Прогресс + инкрементальные сохранения + категории (merged Feb 26, 2026)
- [x] PR #17 — Drop LangChain, unify via LiteLLM (merged Feb 25, 2026)
- [x] First full oneTBB evaluation run (Feb 25, 2026) — baseline established
