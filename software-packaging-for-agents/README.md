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

### Competitive signal: peers already ship an org-level catalog, not just one collection

`intel-performance-skills` is one hand-authored collection. NVIDIA and AMD have
already gone a step further and stood up a **dedicated org-level catalog repo**:

- [`nvidia/skills`](https://github.com/NVIDIA/skills) — mirrors skills daily from
  their owning product repos into one catalog, requires every entry to carry a
  `SKILL.md` + `skill-card.md` + a detached signature (`skill.oms.sig`) + a
  Tier-3 eval dataset, and its roadmap explicitly lists syndication to external
  marketplaces (Skills.sh, Codex plugin, Claude Code plugin, ClawHub, Hermes Hub).
- [`amd/skills`](https://github.com/amd/skills) — "Official AMD catalog of AI
  agent skills," positioned to expose AMD's optimized SW stack to agents the
  same way.

Intel has no equivalent **catalog-of-catalogs** yet — `intel/intel-performance-skills`
is a single collection, not an org-wide entry point. [`napetrov/skills`](https://github.com/napetrov/skills)
is an existing working prototype of that missing layer: a CLI-installable
catalog (`npx @napetrov/intel-skills`, plus the emerging common `npx skills add`
layout) with per-skill `skill-card.md`/`skill-card.json` + `BENCHMARK.md` and a
documented trust model — the same shape as `nvidia/skills` and `amd/skills`, just
not yet an org-official Intel repo. It is a candidate seed/starting point for an
**`intel/skills`** catalog, playing the same "seed, not a replacement" role for
the *catalog* track that `intel-performance-skills` plays for individual skills.

This raises a distribution question the [packaging](packaging.md) open questions
now track explicitly: once Intel has a catalog, **where does it get listed?**
skills.sh already indexes NVIDIA- and Anthropic-published skills; NVIDIA's own
roadmap names several other emerging marketplaces (ClawHub, Hermes Hub, Codex/Claude
plugin listings). That decision is coupled to [attestation](attestation.md), since
NVIDIA ties its marketplace syndication to signed provenance, not just presence.

**Proposed:** [`catalog-distribution.md`](catalog-distribution.md) — DRAFT, for
team review — evaluates the two catalogs above plus the Anthropic Agent Skills
spec and `intel/intel-performance-skills`, and proposes three answers: a
**tiered publishing model** (simple, self-contained skills publish in full;
skills with bundled scripts, setup guides, or fast-moving upstream content
publish as a thin reference wrapper instead — see [`napetrov/skills`](https://github.com/napetrov/skills)'s
`linux-perf-repair` for the existing shape of that wrapper), the **benchmark as
the shared quality gate** for both tiers, and **Intel as the signing/certificate
authority** for the catalog's credential, rather than GitHub-attestation-only.
None of this is a team decision yet.

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
| [`catalog-distribution.md`](catalog-distribution.md) | **`intel/skills` catalog (cross-cutting)** — peer-catalog evaluation, tiered publishing (direct vs. reference), benchmark as the shared quality gate, Intel as signing authority. | Draft |

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
