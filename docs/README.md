# Documentation index

Start with the top-level [README](../README.md) for the project overview and
CLI surface. The files in this directory go deeper:

## Using doc-benchmark

- [quickstart.md](quickstart.md) — end-to-end LLM evaluation pipeline:
  personas → questions → answers → judge → report. Includes troubleshooting
  and a cost estimate.
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
