# Agent measurement framework

Documentation, skills, MCP doc sources and agent persona prompts are cheap to
write and easy to over-claim. This repository is the framework that measures
whether any of them actually helps a coding agent: change one thing, hold
everything else fixed, run the same question or task set, and report the delta
together with its p-value.

The measurement is the deliverable. An artifact ships with the scorecard that
earned it — a deliberate contrast to popularity-ranked marketplaces, which
structurally bury niche HPC and numerical-accuracy tooling.

Beyond question-answer quality, the framework also covers executable
Docker coding tasks run through Codex, Claude Code or Harbor harnesses,
file/line localization (ExploreBench), what a skill's content adds to a given
model (content novelty), whole repositories as evaluation subjects, and
LLM-free static checks on the documentation itself. The framework is
vendor-neutral: any model reachable through LiteLLM, any docs, skills or tasks.

## Repository layout

```text
README.md                          This overview
Makefile                           Delegates targets into agent-benchmark/
agent-benchmark/                   The framework (self-contained Python project)
LICENSE  NOTICE                    Apache-2.0 + attribution (repo-wide)
.github/workflows/                 CI (runs inside agent-benchmark/)
```

All code, tests and CI live in [`agent-benchmark/`](agent-benchmark/). The
evaluation content that gets measured — skills, executable tasks, golden
question sets — lives in its own repository and is passed in by path, so the
framework can measure artifacts it does not own.

## Getting started

```bash
make benchmark-run    # delegates into agent-benchmark/ (see its README)
make test             # runs the agent-benchmark test suite
```

For the framework's quickstart, CLI surface, and architecture, see
[`agent-benchmark/README.md`](agent-benchmark/README.md).

## Where to start reading

| You want to understand… | Read |
|---|---|
| Why measure context at all, and what an arm is | [`agent-benchmark/docs/README.md`](agent-benchmark/docs/README.md) |
| How to point the framework at your own questions, tasks and skills | [`agent-benchmark/docs/external-content.md`](agent-benchmark/docs/external-content.md) |
| How the measurement engine works | [`agent-benchmark/docs/architecture.md`](agent-benchmark/docs/architecture.md) |
| How to run an evaluation end to end | [`agent-benchmark/docs/quickstart.md`](agent-benchmark/docs/quickstart.md) |
| How to compare treatment arms (docs / skills / profiles) | [`agent-benchmark/docs/evaluating-treatments.md`](agent-benchmark/docs/evaluating-treatments.md) |
| How coding agents are run against executable Docker tasks | [`agent-benchmark/docs/coding-harnesses.md`](agent-benchmark/docs/coding-harnesses.md) |
| What a skill actually adds to a model, and what can be cut | [`agent-benchmark/docs/skill-novelty.md`](agent-benchmark/docs/skill-novelty.md) |
| How a whole repository is evaluated as a subject | [`agent-benchmark/docs/repo-evaluation-contract.md`](agent-benchmark/docs/repo-evaluation-contract.md) |
| What products are registered | [`agent-benchmark/products.yaml`](agent-benchmark/products.yaml) |
| What user problems map to which product | [`agent-benchmark/intents.yaml`](agent-benchmark/intents.yaml) |

## License

Licensed under the [Apache License, Version 2.0](LICENSE); see [NOTICE](NOTICE)
for attribution.
