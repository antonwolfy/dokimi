# Software Packaging for Agents — framing & architecture

This directory holds the **vision and architecture** for packaging software so
that *agentic AI consumers* — not just human developers — can discover, install,
and use it effectively. The companion [`../agent-benchmark/`](../agent-benchmark/)
provides the measurement engine that decides whether a packaged artifact is
actually worth shipping.

> **Status:** Framing in progress on the `packaging-distribution-vision` branch.
> The architecture and the design docs for all six tracks are drafted; see the
> umbrella [README](../README.md) for the project loop and the architecture
> mainline being explored.

## Why this exists — the product is a summonable Intel expert

Software distribution is reorganizing around agents. The deliverable we aim at is
not a file but an **expert you can spawn**:

> Spawn an Intel expert for a specific Intel **software or hardware** product
> problem, pre-equipped with all the skills and MCP sources that expert needs.

To make that expert real, competent, and trustworthy, we package **agent-facing
capabilities** and prove them:

- **Agent profiles** — the persona/system prompt that *is* the expert's face.
- **Skills** — packaged, triggerable know-how (`SKILL.md` + idioms + BKMs +
  optional scripts).
- **Setup guides** — executable, verified environment bootstrap (critical for
  hardware experts).
- **MCP doc sources** — on-demand access to the relevant slice of documentation.

The mainline hypothesis: *documentation behaves as a general skill, and MCP (or
an equivalent) is how an agent asks for the relevant part on demand* — a thin,
always-available skill that knows when to reach for a thick doc source. The
[benchmark](../agent-benchmark/) is the gate that makes the expert *vetted, not
merely listed*.

## Prior art: Intel skills already shipping

The skills artifact is not hypothetical — Intel already publishes skill
collections in the open [Agent Skills](https://github.com/intel/intel-performance-skills)
format. [`intel/intel-performance-skills`](https://github.com/intel/intel-performance-skills)
(among others) is a seed-shaped **Intel-aware optimization expert**: three
composable `SKILL.md` skills — `linux-perf` (profile with `perf`) hands off to
`performance-patterns` (a fix playbook: serial accumulators, narrow SIMD, missing
`vzeroupper`/`restrict`, false sharing, …), which can auto-invoke
`phoronix-test-suite`. It targets x86/AVX2/AVX-512, installs cross-runtime
(Claude Code, Copilot, Codex, Gemini CLI) via `gh skill install`, and triggers on
natural phrases like "why is this slow."

It validates three things this project builds on:

- **The artifact and format are real** — composable `SKILL.md` skills following an
  open standard, exactly our skills layer.
- **Cross-runtime distribution already works** — strong evidence that an Agent
  Skills exporter is the natural *first* target (see [`packaging.md`](packaging.md)
  §5, per-runtime exporters).
- **Skill composition / hand-off** — one skill delegating to another, the seed of
  the [serve-track router](serving.md).

What it does *not* yet carry is the rest of our cycle: a benchmarked **scorecard**,
a problem-scoped **persona**, on-demand **MCP** doc retrieval, a verified
**setup-guide**, and **discovery** by fit. Those are what turn a shipped skill
collection into a *summonable, vetted expert*. Such repos are seeds for the
[author](authoring.md) and [serve](serving.md) tracks, not a replacement for them.

## Contents

The project is a closed cycle of six tracks (see [`architecture.md`](architecture.md)):
**author → build → measure → package → discover → serve**, with a feedback loop
back to author/measure.

| File | Track | Status |
|---|---|---|
| [`architecture.md`](architecture.md) | The six-track cycle and how the parts compose. | Draft |
| [`authoring.md`](authoring.md) | **Author** — distill skills from docs (benchmark as fitness function) + the executable setup-guide artifact. | Draft |
| [`packaging.md`](packaging.md) | **Package** — the agent-package manifest, the two-tier BKM, evidence-as-credential, and per-runtime exporters. | Draft |
| [`discovery.md`](discovery.md) | **Discover** — capability/intent graph + semantic search, ranked by vetted scorecard rather than popularity. | Draft |
| [`serving.md`](serving.md) | **Serve** — spawning a problem-scoped Intel expert; the graph as a fleet router; telemetry out. | Draft |
| [`feedback.md`](feedback.md) | **Loop** — telemetry + freshness re-score the scorecard so the credential stays living. | Draft |
| [`attestation.md`](attestation.md) | **Trust (cross-cutting)** — the scorecard as a signed, portable credential other catalogs can verify. | Draft |

## The discovery problem

Marketplaces rank by popularity / "what's trending." That structurally buries
niche HPC and numerical-accuracy tools, which will never trend among average
developers. The planned discovery layer replaces keyword/trend ranking with a
**capability/intent graph + semantic search**, using the benchmark scorecard as
a *vetted* ranking signal. See [`discovery.md`](discovery.md).

## Relationship to `agent-benchmark/`

`agent-benchmark/` already contains the primitives this framing packages —
treatment arms for `agent_profile`, `skill`, and `mcp` (see
[`../agent-benchmark/docs/evaluating-treatments.md`](../agent-benchmark/docs/evaluating-treatments.md)).
Here those primitives are treated as **deliverables to ship**, not just
benchmark inputs to score.
