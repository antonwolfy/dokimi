# Software Packaging for Agents

Usage is shifting from human developers to **agentic AI consumers**. Software —
especially expert, high-performance, and numerically-sensitive Intel software and
hardware — needs to be packaged for *that* audience: reachable by an agent,
practical to apply, and carrying its own best-known-methods (BKMs), setup
guidance, and idioms.

The deliverable is a **summonable Intel expert**:

> Spawn an Intel expert for a specific Intel software or hardware product
> problem, pre-equipped with all the skills and MCP sources that expert needs.

This repository pursues that mission in two complementary halves:

| Directory | Role | Status |
|---|---|---|
| [`software-packaging-for-agents/`](software-packaging-for-agents/) | **Framing & architecture** — the vision, the agent-package format, per-runtime distribution (Claude, Hermes, …), and the discovery layer. | Bootstrapping |
| [`doc-benchmark/`](doc-benchmark/) | **Measurement engine** — evaluates whether a given skill / MCP doc source / agent profile actually improves agent answers and task outcomes. The evidence that justifies shipping an artifact. | Established |

## The cycle

```text
   author ─► build ─► measure ─► package ─► discover ─► serve
  (distill           (doc-bench: (manifest  (capability  (spawn the
   skills +           arms,       + score-   graph,        problem-scoped
   setup              judges,     card,      ranked by     expert; BKM runs;
   guides)            tasks)      exporters) fit not       telemetry out)
      ▲                                       trend)            │
      └───────── feedback: telemetry + freshness re-score ──────┘
```

Measurement is the **gate**, not the product: a spawned expert ships with the
scorecard that earned it — a deliberate contrast to popularity/trend-ranked
marketplaces, which structurally bury niche HPC and numerical-accuracy tools. The
feedback loop keeps that scorecard *living* as real usage and upstream docs
change.

## Architecture mainline being explored

> Intel expert persona → system prompt, skills, and MCP, distributed as an
> agent for Claude, Hermes, et al. Documentation behaves as a *general skill*;
> MCP (or equivalent) is how the agent asks for the relevant part on demand.

See [`software-packaging-for-agents/`](software-packaging-for-agents/) for the
full framing and architecture.

## Repository layout

```text
README.md                          This umbrella overview
Makefile                           Delegates targets into each area
software-packaging-for-agents/     Framing & architecture (author/package/discover/serve/feedback)
doc-benchmark/                     The measurement engine (self-contained Python project)
LICENSE  NOTICE                    Apache-2.0 + attribution (repo-wide)
.github/workflows/                 CI (runs inside doc-benchmark/)
```

## Getting started

The runnable project today is the benchmark:

```bash
make benchmark        # delegates into doc-benchmark/ (see its README)
make test             # runs the doc-benchmark test suite
```

For the benchmark's own quickstart, CLI surface, and architecture, see
[`doc-benchmark/README.md`](doc-benchmark/README.md).

## License

Licensed under the [Apache License, Version 2.0](LICENSE); see [NOTICE](NOTICE)
for attribution.
