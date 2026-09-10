# Architecture overview

`agent-benchmark` ships two parallel evaluation tracks plus an optional
executable-task suite. They share configuration (`config/products.yaml`,
`products.yaml`, `intents.yaml`) and a single CLI entry point (`cli.py`) but
otherwise operate independently.

```text
                       ┌──────────────┐
                       │   cli.py     │   single argparse front-end
                       └──┬────────┬──┘
                          │        │
       ┌──────────────────┘        └────────────────────┐
       ▼                                                ▼
┌────────────────┐                          ┌──────────────────────────┐
│ Static track   │                          │ LLM evaluation track     │
│                │                          │                          │
│ ingest/        │ Markdown files           │ personas/                │
│   └─ chunking  │                          │ questions/               │
│ metrics/       │ coverage, freshness,     │ mcp/      (context fetch) │
│   └─ scoring   │ readability, examples    │ eval/     (judges, RAGAS)│
│ gate/          │ soft/hard/critical gates │ report/   (analysis)     │
│ runner/        │ orchestration + compare  │ dashboard/(aggregation)  │
│ report/        │ JSON + Markdown out      │                          │
└──────┬─────────┘                          └──────────┬───────────────┘
       │                                               │
       └───────────────► baselines/  reports/  ◄───────┘
                            (JSON / Markdown artifacts)

                       ┌─────────────────────────────────┐
                       │ external tasks root             │
                       │  (--tasks-root <checkout>)      │
                       │  Docker + oracle + pytest       │
                       │  exercised by GitHub Actions    │
                       └─────────────────────────────────┘
```

## Static documentation track

Lives entirely under `agent_benchmarks/{ingest,metrics,gate,runner,report}`.

1. `ingest/` walks the configured root, loads Markdown files, and produces
   per-file text.
2. `metrics/` scores each file. Each metric is a small pure module:
   `coverage`, `freshness_lite`, `readability`, `example_pass_rate`. See
   [contributing-metric.md](contributing-metric.md) for how to add one.
3. `runner/run.py` reads `benchmarks/spec.v1.yaml`, runs the enabled
   metrics, normalizes weights, and writes a snapshot JSON.
4. `gate/` applies soft gates, hard gates, critical bands, and regression
   thresholds (`runner/compare.py` powers `cli.py compare`).
5. `report/` turns snapshots and comparisons into Markdown.

Entry points: `python cli.py run`, `python cli.py compare`, `python cli.py
report`.

## LLM evaluation track

Lives under `agent_benchmarks/{personas,questions,mcp,eval,report,dashboard,orchestrator}`.

1. `personas/` discovers and validates target user personas from GitHub
   activity.
2. `questions/` generates, dedupes, and validates persona-driven questions,
   plus document-grounded questions ("hybrid generation").
3. `mcp/` retrieves documentation chunks for each question. The default
   client is Context7 over HTTP (`mcp/context7.py`); `mcp/factory.py`
   dispatches `--doc-source` to alternative clients (`local:`, `url:`, or a
   custom registered client — see
   [adding-doc-source.md](adding-doc-source.md)).
4. `eval/` runs answer generation (`llm.py`), single-judge scoring, the
   multi-judge panel, and RAGAS meta-evaluation.
5. `report/eval_report.py` produces the per-product Markdown analysis.
6. `dashboard/` aggregates per-library results into a cross-library view
   (`DASHBOARD.md`, `dashboard.json`).
7. `orchestrator/` wires steps 1–5 together for the `evaluate` one-command
   pipeline.

Entry points: `python cli.py {personas,questions,answers,eval,report,
dashboard,evaluate}`.

The full step-by-step recipe is in [quickstart.md](quickstart.md).

### Treatment-arm comparison

The two-arm `with_docs`/`without_docs` answerer is generalized by
`agent_benchmarks/treatments/` into an N-way comparison of
context-augmentation treatments. A `Treatment` produces an `AgentConfig`
(system prompt + injected context) per question; arms cover documentation
injection (`docs`/`mcp:`), agent persona prompts (`profile:`, loaded from
`agent_profiles/`), skills (`skill:`, loaded from `skills/`), and agentic use
where the model decides to call a doc-search or skill tool (`agent:`,
`skill-agent:`) via the tool-calling loop in `eval/agent_runner.py`.
`eval/arm_runner.py` generates and judges answers for every arm and reports
per-arm deltas vs a baseline. Entry point: `python cli.py arms run`. Details in
[evaluating-treatments.md](evaluating-treatments.md) and
[decisions/2026-05-29-evaluating-mcp-skills-personas.md](decisions/2026-05-29-evaluating-mcp-skills-personas.md).

## Executable task track

Tasks are [Terminal-Bench / Harbor](https://harborframework.com)-format
directories — Docker environment, `instruction.md`, oracle solution, and pytest
verifier — supplied from an external content checkout named with `--tasks-root`
(format spec:
[contributing-terminal-bench-task.md](contributing-terminal-bench-task.md)). CI
builds a container from a pinned external catalog and runs its oracle to make
sure the harness, the task format, and the verifier path all still work.

`agent_benchmarks/harnesses/` turns those task directories into measured
`task_runs.v1` artifacts. Built-in harness aliases include `codex`,
`claude-code`, and `terminal-bench:<agent>`; each runs a Harbor-compatible agent,
records operation telemetry (`harness`, `loop`, `tool`, `subagent`, ...), and
summarizes pass-rate deltas against a baseline harness. Entry point:
`python cli.py tasks run`.

See [contributing-terminal-bench-task.md](contributing-terminal-bench-task.md)
to add a task and [coding-harnesses.md](coding-harnesses.md) to run harness
comparisons.

Skills and tasks don't have to live in this repo: `agent_benchmarks/external/`
reads another checkout's own manifests (`skills.yaml`,
`evaluation/harbor/suites.json` — the uxlfoundation/skills convention) and
reports what loads via `python cli.py catalog scan --root <path>`; loaded
entries then plug into the same `--tasks-root` / `docker-claude-skill:<path>`
flags as local ones. [external-content.md](external-content.md) is the
end-to-end walkthrough of that; the "External Sources" section of
[coding-harnesses.md](coding-harnesses.md) covers the harness-specific part.

## Shared building blocks

- `agent_benchmarks/llm.py` — provider-neutral LLM call wrapper (LiteLLM-based)
  with retry, token accounting, and concurrency.
- `agent_benchmarks/registry.py` — product registry loaded from
  `products.yaml`; powers `cli.py library` (alias `product`) and
  `cli.py benchmark`.
- `agent_benchmarks/intents.py` — intent registry loaded from `intents.yaml`:
  the problem/intent space mapping domains (data science, debugging,
  optimization, …) to the products that serve them. Consistency with
  `products.yaml` is enforced by `python -m agent_benchmarks.config_check`.
- `config/products.yaml` — per-product config: GitHub repo, Context7 ID,
  retrieval defaults, judge model, persona count.
- `benchmarks/spec.v1.yaml` + `benchmarks/spec.schema.json` — declarative
  static-benchmark configuration.

## CI

Two GitHub Actions workflows run on PRs (see `.github/workflows/`):

**`ci.yml`** — fast code checks:

1. **lint** — `ruff check .`.
2. **mypy** — type check.
3. **schema** — `schema_check` validates `benchmarks/spec.v1.yaml`;
   `config_check` checks `products.yaml`/`intents.yaml`/`config/products.yaml`
   drift.
4. **test** — pytest with coverage (Python 3.10–3.13).
5. **package-smoke** — builds/installs the package and exercises the console and
   module entry points.

**`agent-quality.yml`** — task and benchmark checks:

6. **external-catalog-smoke** — clones a pinned external content catalog, runs
   `catalog scan` over it, then drives one of its real tasks through the
   `docker-oracle` harness (build + solve + verify, `--network none` at solve and
   verify time) and asserts the pass rate. Task definitions are not in this
   repository, so this job proves the harness and the task format rather than any
   particular task.
7. **benchmark** — runs the static agent-quality benchmark and uploads
   `current.json` / `current.md` artifacts.

Manual workflow dispatch on `agent-quality.yml` supports `--strict` for
blocking quality gates.
