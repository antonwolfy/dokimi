# Documentation index

Start with the top-level [README](../README.md) for the project overview and
CLI surface. The files in this directory go deeper:

## Using doc-benchmark

- [quickstart.md](quickstart.md) — end-to-end LLM evaluation pipeline:
  personas → questions → answers → judge → report. Includes troubleshooting
  and a cost estimate.
- [benchmarking-and-comparison.md](benchmarking-and-comparison.md) — how to
  run static benchmarks, LLM context benchmarks, fair multi-model comparisons,
  treatment-arm comparisons, dashboards, baselines, and PR #60 comparison
  scripts.
- [adding-doc-source.md](adding-doc-source.md) — point the pipeline at local
  files, a single URL, a real MCP server, or a custom client.
- [evaluating-treatments.md](evaluating-treatments.md) — compare
  context-augmentation arms (docs, MCP, skills, agent persona prompts) with
  `cli.py arms run`.

## Extending doc-benchmark

- [architecture.md](architecture.md) — module map and data flow across the
  static, LLM, and executable-task tracks.
- [contributing-metric.md](contributing-metric.md) — add a new static
  documentation metric (module + spec + tests + docs).
- [contributing-terminal-bench-task.md](contributing-terminal-bench-task.md)
  — add an executable oneTBB / oneAPI task with Docker, oracle, and pytest
  verifier.

## Historical decisions

The `decisions/` directory keeps point-in-time design reviews and
investigations. They reflect the state of the project at their dated time
and may have been partially superseded — each file's header notes its
current status.

- [decisions/2026-02-12-review-devils-advocate.md](decisions/2026-02-12-review-devils-advocate.md)
- [decisions/2026-02-12-review-intel-product.md](decisions/2026-02-12-review-intel-product.md)
- [decisions/2026-02-14-context7-http-vs-mcp.md](decisions/2026-02-14-context7-http-vs-mcp.md)
- [decisions/2026-05-29-evaluating-mcp-skills-personas.md](decisions/2026-05-29-evaluating-mcp-skills-personas.md)
  — assessment + proposal for evaluating MCP docs, skills, and agent persona
  prompts as first-class treatment arms.
- [decisions/2026-06-10-evaluation-beyond-mcp-docs.md](decisions/2026-06-10-evaluation-beyond-mcp-docs.md)
  — **umbrella / index** for extending evaluation beyond MCP docs; states the
  shared motivation and sequences the three ADRs below.
  - [decisions/2026-06-10-questions-and-tasks-coverage-contract.md](decisions/2026-06-10-questions-and-tasks-coverage-contract.md)
    — pair every project's question set (awareness) with an executable task set
    (work); surface the gap as a checked matrix. *(Phase A.)*
  - [decisions/2026-06-10-model-harness-dimension.md](decisions/2026-06-10-model-harness-dimension.md)
    — make base model × harness an explicit, swept, reported dimension; deltas
    only comparable within a `(model, harness)` cell. *(Phase B.)*
  - [decisions/2026-06-10-artifacts-as-evaluation-subjects.md](decisions/2026-06-10-artifacts-as-evaluation-subjects.md)
    — promote skills/profiles/bundles from arms to first-class evaluation
    *subjects* emitting a per-subject scorecard. *(Phase C.)*
- [decisions/benchmark-methodology.md](decisions/benchmark-methodology.md)
  — current operational methodology for model roles, question types,
  difficulty levels, answer generation, judging, trust checks, and executable
  agent tasks.
