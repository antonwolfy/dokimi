# BACKLOG

## Active

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
