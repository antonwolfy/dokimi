# doc-benchmark

`doc-benchmark` is a toolkit for measuring and improving technical documentation quality. It supports two complementary workflows:

1. **Static documentation quality checks** over Markdown/code examples: coverage, freshness, readability, example execution, gates, and regression detection.
2. **LLM-assisted product documentation evaluation**: persona and question generation, answer generation with/without documentation context, LLM-as-judge scoring, multi-judge panels, RAGAS meta-evaluation, dashboards, and executable terminal-bench-style tasks.

The repository is currently focused on Intel library documentation quality experiments, especially oneTBB, oneDAL, and oneMKL.

## Quick start

Install dependencies:

```bash
pip install -r requirements.txt
pip install -r requirements-test.txt
```

Run the static documentation benchmark:

```bash
python cli.py run \
  --root . \
  --spec benchmarks/spec.v1.yaml \
  --out-json baselines/current.json \
  --out-md reports/current.md
```

Compare a candidate snapshot with a baseline:

```bash
python cli.py compare \
  --base baselines/baseline.json \
  --candidate baselines/current.json \
  --spec benchmarks/spec.v1.yaml \
  --out-json reports/compare.json \
  --out-md reports/compare.md
```

Run the test suite:

```bash
python -m pytest -q
```

For the LLM evaluation pipeline (answers, judging, dashboard), see [docs/quickstart.md](docs/quickstart.md). A high-level architecture map is in [docs/architecture.md](docs/architecture.md), and [docs/README.md](docs/README.md) is the documentation index.

## Main CLI areas

The top-level CLI is `python cli.py`. The main command groups are:

```text
run                 Run the static docs-quality benchmark
compare             Compare benchmark snapshots
report              Render JSON reports to Markdown
evaluate            Run the full evaluation pipeline
personas            Discover and approve target user personas
questions           Generate, analyze, refine, and panel-review questions
answers             Generate answers with and without documentation context
arms                Compare context-augmentation treatments (docs/MCP/skills/profiles)
eval                Score answers, run RAGAS, or use a multi-judge panel
library             List/show registered libraries
benchmark           Run registered library benchmarks
dashboard           Generate dashboard Markdown/JSON
```

Use `--help` on any command for detailed options, for example:

```bash
python cli.py questions --help
python cli.py eval --help
python cli.py dashboard generate --help
```

## Static benchmark metrics

The default static benchmark is configured in `benchmarks/spec.v1.yaml` and currently uses four active metrics:

| Metric | Purpose |
| --- | --- |
| `coverage` | Checks Markdown structure: headings, code blocks, and body content. |
| `freshness_lite` | Scores files by modification age. |
| `readability` | Estimates text readability with a Flesch-Kincaid-style score. |
| `example_pass_rate` | Executes supported fenced code examples in isolation. |

Weights are normalized across enabled metrics. The benchmark also supports soft gates, hard gates, critical bands, and regression thresholds. Hard gates and critical bands are enforced only when `--strict` is passed.

## LLM evaluation workflow

The LLM workflow is designed to answer a practical question: does documentation improve model answers for real developer tasks?

A typical flow is:

```bash
python cli.py personas discover ...
python cli.py questions generate ...
python cli.py questions refine ...
python cli.py answers generate ...
python cli.py eval score ...
python cli.py eval panel-score ...
python cli.py eval ragas ...
python cli.py dashboard generate ...
```

Generated artifacts should normally go under `results/`, `reports/`, or `baselines/current.json` for temporary runs; those paths are ignored by default. Curated fixtures under `answers/`, `eval/`, `baselines/`, and `questions/` may be committed intentionally when they are part of a reproducible benchmark.

## Executable oneTBB tasks

The repository includes terminal-bench-style tasks under `terminal-bench-tasks/`. These tasks validate not just text answers but working code and measurable behavior. Current CI verifies oracle solutions for the included oneTBB task.

Planned next work is to derive additional oneTBB executable tasks from [ParRes/Kernels](https://github.com/ParRes/Kernels), with provenance/license checks before adapting code. Good first candidates are `nstream`, `stencil`, `transpose`, `sparse`, and shared-memory adaptations of `p2p` patterns.

## Repository layout

```text
cli.py                   Single entry point for all CLI commands
benchmarks/              Static benchmark spec and schema
config/                  Product/library configuration
libraries.yaml           Registered libraries for the LLM evaluation pipeline
doc_benchmarks/          Main Python package
  agent_profiles/        Agent persona prompt loader
  dashboard/             Dashboard aggregation/rendering
  eval/                  Answer generation, judges, panels, RAGAS, arm runner
  gate/                  Soft/hard gates and regression classification
  ingest/                Markdown loading and chunking
  mcp/                   Documentation source clients (incl. MCP protocol)
  metrics/               Static documentation metrics
  orchestrator/          Pipeline orchestration
  personas/              Persona generation/analysis (synthetic users)
  questions/             Question generation, validation, refinement
  report/                JSON/Markdown report generation
  runner/                Benchmark orchestration
  skills/                SKILL.md loader
  treatments/            Treatment-arm abstraction (docs/MCP/skills/profiles)
agent_profiles/          Agent persona prompt fixtures
skills/                  Agent skill (SKILL.md) fixtures
answers/, eval/,         Curated fixtures used by the evaluation pipeline
  questions/,
  baselines/,
  api_ground_truth/
docs/                    Documentation
  README.md              Documentation index
  quickstart.md          End-to-end LLM evaluation pipeline
  architecture.md        Module map and data flow
  adding-doc-source.md   Local/URL/custom doc sources
  contributing-metric.md How to add a static documentation metric
  contributing-terminal-bench-task.md
                         How to add an executable task
  decisions/             Historical design reviews and investigations
terminal-bench-tasks/    Executable task definitions and verifiers
  README.md              Task format reference and task table
  COVERAGE.md            API/concept coverage matrix
  PROVENANCE.md          Upstream sources and licensing notes
tests/                   Pytest suite
```

## CI

GitHub Actions runs three checks on pull requests:

1. `test` — installs `requirements-test.txt` and runs pytest with coverage.
2. `benchmark` — runs the static docs-quality benchmark and uploads artifacts.
3. `Verify terminal-bench-tasks` — builds task containers and verifies oracle solutions.

Manual workflow dispatch supports strict mode for blocking quality gates.

## Repository hygiene

Do not commit generated logs, coverage databases, tarballs, local caches, or one-off experiment outputs. Keep generated benchmark artifacts either ignored locally or explicitly curated as fixtures. Use pull requests for all changes to `main`.

Status reports, phase plans, and other development-history notes do not belong in the repository — work-in-progress should live in PR descriptions, issues, and `BACKLOG.md`.

## Contributing

- Run `python -m pytest -q` before opening a PR.
- See [docs/contributing-metric.md](docs/contributing-metric.md) and
  [docs/contributing-terminal-bench-task.md](docs/contributing-terminal-bench-task.md)
  for the two main extension flows.
- Keep generated artifacts under `reports/` or `results/` (both ignored).
  Only commit curated fixtures that are part of a reproducible benchmark.

## License

Licensed under the [Apache License, Version 2.0](LICENSE). See [NOTICE](NOTICE)
for attribution. Contributions are accepted under the same license — see
[CONTRIBUTING.md](CONTRIBUTING.md). To report a security issue, see
[SECURITY.md](SECURITY.md).
