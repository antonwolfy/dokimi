# Architecture overview

`agent-benchmark` ships two parallel evaluation tracks, an optional
executable-task suite, and two tracks that change the *question* rather than the
pipeline: content novelty (what does an artifact add to a model?) and
repositories as evaluation subjects (can a repo supply its own tasks?). They
share configuration (`config/products.yaml`, `products.yaml`, `intents.yaml`)
and a single CLI entry point (`cli.py`) but otherwise operate independently.

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

┌───────────────────────────────┐   ┌───────────────────────────────┐
│ Content novelty               │   │ Repository as subject         │
│                               │   │                               │
│ novelty/   atoms → paired     │   │ repos/     repo-eval.yaml +   │
│            probes → 2×2       │   │            task.json from the │
│ gate/      novelty gates      │   │            scanned repo       │
│                               │   │ profiles/  one YAML per agent │
│ asks: what does this artifact │   │ asks: does the repo's own     │
│ add to *this* model?          │   │ guidance reach the agent?     │
└───────────────────────────────┘   └───────────────────────────────┘
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
[evaluating-treatments.md](evaluating-treatments.md).

## Content-novelty track

An arm comparison produces one number for a whole artifact: it helps, or it does
not. That is enough to ship or cut a skill and not enough to *edit* one, because
a skill is not homogeneous — part of it teaches the model something, part of it
is the model's own prior knowledge written down, and part of it can make the
model worse. `agent_benchmarks/novelty/` splits that single delta per sentence.

The mechanism is a paired probe. The artifact is cut into spans, checkable
knowledge atoms are extracted from those spans, and every atom is asked of the
same model twice — once with no artifact in context, once with it. A *different*
model grades both answers, so the four outcomes (`added`, `redundant`,
`degraded`, `still_missing`) are exhaustive and the comparison survives a judge
whose absolute calibration is poor.

1. `agent_benchmarks/novelty/spans.py` segments the artifact;
   `agent_benchmarks/novelty/atoms.py` extracts atoms and verifies each one
   against the span cited for it.
2. `agent_benchmarks/novelty/needs.py` builds a need graph from the artifact's
   `name` and `description` *only* — never from its body — so relevance has a
   scope the artifact cannot define for itself.
3. `agent_benchmarks/novelty/probes.py` builds the paired probes;
   `agent_benchmarks/novelty/measure.py` runs them over the configured arms
   (`no_artifact`, `full`, and the optional `placebo` and `shuffled` controls)
   and raises rather than let a model grade itself.
4. `agent_benchmarks/novelty/classify.py` judges content categories;
   `agent_benchmarks/novelty/attribute.py` maps outcomes back to spans, topics,
   and terms.
5. `agent_benchmarks/novelty/shorten.py` scores shortening candidates on five
   separate axes (tokens, knowledge, value, protection, routing), with a
   cache-backed retention oracle in `agent_benchmarks/novelty/retention.py`.
6. `agent_benchmarks/novelty/report.py` writes the scorecard block and an
   annotated HTML view of the artifact; `agent_benchmarks/gate/novelty_gate.py`
   turns the numbers into soft gates.

Entry points: `python cli.py novelty {analyze,atoms,probe,shorten,view}`, and
`python cli.py subjects run` to carry the result on a subject scorecard over
time.

Novelty is a property of the (artifact, model) pair, not of the file — the same
skill is worth very different amounts to a frontier and to a small model, so the
model under measurement is always recorded with the result. `--model` defaults to
`gpt-4o-mini`; pass it explicitly, or the run measures that model instead of the
one you meant.
[skill-novelty.md](skill-novelty.md) is the authoring guide;
[skill-novelty-evidence.md](skill-novelty-evidence.md) is the study the default
thresholds come from, with the caveat attached to each number.

## Executable task track

Tasks are [Terminal-Bench / Harbor](https://harborframework.com)-format
directories — Docker environment, `instruction.md`, oracle solution, and pytest
verifier — supplied from an external content checkout named with `--tasks-root`
(format spec:
[contributing-terminal-bench-task.md](contributing-terminal-bench-task.md)). CI
builds a container from a pinned external catalog and runs its oracle and the
isolation probe, to make sure the harness, the task format, the verifier path
and the agent's sandbox all still work.

`agent_benchmarks/harnesses/` turns those task directories into measured
`task_runs.v1` artifacts. Built-in harness aliases include `codex`,
`claude-code`, and `terminal-bench:<agent>`; each runs a Harbor-compatible agent,
records operation telemetry (`harness`, `loop`, `tool`, `subagent`, ...), and
summarizes pass-rate deltas against a baseline harness. Entry point:
`python cli.py tasks run`. Three modules own the solver's launch:

- `harnesses/container_agent.py` runs the agent in the task container, on an
  internal network.
- `harnesses/egress_proxy.py` is the allowlisting proxy that container's only
  way out goes through.
- `harnesses/agent_sandbox.py` is the host launch for the `-host` variants,
  and holds the `docker-probe` isolation probe that measures both launches.

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

## Repositories as evaluation subjects

The tracks above measure an artifact the framework is handed. This one turns the
question around: a *repository* declares what evaluating it means, and the
framework runs that. The subject is no longer a skill but the repo's own agent
guidance — `CLAUDE.md`, `AGENTS.md`, `.github/copilot-instructions.md`,
contributor docs — and the question is whether that guidance reaches an agent
and changes what it produces.

The split is deliberate: tasks, graders, and the manifest live **in the scanned
repository**, not here (`agent_benchmarks/repos/` only reads them). A repo
evolves with its own tasks; a copy of them in this tree would be stale by the
next release.

- `agent_benchmarks/repos/manifest.py` — loads and validates `repo-eval.yaml`
  (`repo_manifest.v1`) in two passes: the manifest's own shape, then the
  manifest against one snapshot (declared paths exist, guidance globs match,
  every task directory carries a contract-shaped `task.json`).
- `agent_benchmarks/repos/source.py` — resolves `<dir>`, `<dir>@<rev>` or
  `<url>@<rev>` to a pinned snapshot, cached per URL as a blob-less clone, so a
  run names an exact commit.
- `agent_benchmarks/repos/reach.py` + `agent_benchmarks/repos/harness_profile.py`
  — the reach probe. It does not trust a harness's documented loading rules: it
  builds a skeleton workspace with the repo's guidance files at their real
  paths, plants a head and a tail token in each, and asks the agent which tokens
  it can see. A file comes back `loaded`, `truncated` (one token — the file was
  cut), `fetched` (seen only after the agent read it), `not_loaded`, or `error`
  (no usable answer). Harness behaviour is data, not code:
  `agent_benchmarks/repos/profiles/claude-code.yaml` is a `harness_profile.v1`
  file and any other harness is another YAML.
- `agent_benchmarks/repos/static.py` — the `repo_static.v1` schema: what the
  repository's own `static` entry point writes, so its checks can be merged
  into L0.
- `agent_benchmarks/repos/bases.py` — checks that need every task base: each
  `base` must resolve, and the guidance globs are evaluated at each base.
- `agent_benchmarks/repos/events.py` — converts a harness trace to the
  `events.jsonl` run trace.

Entry points on main today: `python cli.py repo {validate,fetch,reach}`
(`python cli.py repo --help` is the current list). The task-run and grading
half of the contract — the `grade` entry point and `grade.json` — is specified in
[repo-evaluation-contract.md](repo-evaluation-contract.md) and still being built
out; that document is the interface a repository codes against, and it is marked
PROPOSED until the pipeline lands.

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

Three GitHub Actions workflows run on PRs (see `.github/workflows/`). The third,
`contracts.yml`, runs only when a PR touches `agent_benchmarks/schemas/`:
`python -m agent_benchmarks.schema_compat` fails an in-place edit that narrows
an existing schema version, unless a reviewer applies the `schema-break-ok`
label. The other two:

**`ci.yml`** — fast code checks:

1. **lint** — `ruff check .`.
2. **mypy** — type check of the whole package (modules listed in the
   `pyproject.toml` override are exempt until fixed).
3. **schema** — `schema_check` validates `benchmarks/spec.v1.yaml`;
   `config_check` checks `products.yaml`/`intents.yaml`/`config/products.yaml`
   drift.
4. **test** — pytest from `requirements.lock.txt`, offline, with coverage
   (Python 3.10–3.13); on a PR, 80% of the changed lines must be covered.
5. **package-smoke** — builds/installs the package and exercises the console and
   module entry points.

**`agent-quality.yml`** — task and benchmark checks:

6. **external-catalog-smoke** — clones a pinned external content catalog, runs
   `catalog scan` over it, then drives one of its real tasks through the
   `docker-oracle` harness (build + solve + verify, with the task's own
   `network_mode`, bridge for this public task) and the `docker-probe`
   isolation probe. It asserts both pass
   rates, so a launch change that lets an in-container agent reach the grader,
   the skills or the network fails CI. Task definitions are not in this
   repository, so this job proves the harness and the task format rather than any
   particular task.
7. **benchmark** — runs the static agent-quality benchmark with `--strict`, so
   a gate or band failure fails the job, and uploads `current.json` /
   `current.md` artifacts.
