# Architecture (framing skeleton)

> **Status:** Skeleton. This file fixes the shape so contributors know where
> each piece goes; the detailed design lives in [`packaging.md`](packaging.md)
> and [`discovery.md`](discovery.md).

The project is a **closed cycle** of six tracks. Only **measure** is built
today (as [`../agent-benchmark/`](../agent-benchmark/)); the others are the subject
of this directory. The cycle matters more than any single track: artifacts are
authored, proven, shipped, found, *used*, and the evidence from real use flows
back to re-author and re-score them.

```text
        ┌──────────────────────── the feedback loop ───────────────────────────┐
        │                                                                       │
        ▼                                                                       │
  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
  │  AUTHOR  │──►│  BUILD   │──►│ MEASURE  │──►│ PACKAGE  │──►│ DISCOVER │──►│  SERVE   │
  │ distill  │   │ assemble │   │ doc-     │   │ manifest │   │ capability│  │ runtime, │
  │ skills + │   │ profile +│   │ bench:   │   │ + score- │   │ graph +   │  │ BKM runs,│
  │ setup    │   │ skills + │   │ arms,    │   │ card,    │   │ semantic  │  │ telemetry│
  │ guides   │   │ mcp      │   │ tasks    │   │ exporters│   │ search    │  │ out      │
  └──────────┘   └──────────┘   └────┬─────┘   └──────────┘   └──────────┘   └────┬─────┘
       ▲                             │ scorecard (gate)                           │
       │                             └────────────────────────────────────────┐  │
       │   telemetry → new questions → re-score → re-package (the living loop) │  │
       └──────────────────────────────────────────────────────────────────────┴──┘
```

## Tracks

1. **Author** — manufacture the artifacts at scale: distill a thin Tier-1
   `SKILL.md` from a library's docs and iterate it against the benchmark, and
   produce the executable **setup guide** (environment bootstrap) that HPC
   agents actually need. Today only one skill exists, hand-written. Design:
   [`authoring.md`](authoring.md).
2. **Build** — assemble the authored artifacts into an agent configuration
   (`AgentConfig`: system prompt + skills + mcp + tools). Today these exist as
   benchmark fixtures (`../agent-benchmark/data/agent_profiles/`,
   `../agent-benchmark/data/skills/`).
3. **Measure** — `agent-benchmark/`. The scorecard is the gate: only artifacts
   that demonstrably improve answers/task outcomes get packaged. The scorecard
   carries *both* Q&A-judge deltas and behavioral terminal-bench pass-rates.
4. **Package** — serialize the agent configuration (+ scorecard + provenance)
   into a manifest and export it per runtime (Claude plugin, Anthropic Agent
   Skills layout, Hermes, generic). Design: [`packaging.md`](packaging.md).
5. **Discover** — a capability/intent graph with semantic search so niche tools
   surface by *fit*, not popularity. Design: [`discovery.md`](discovery.md).
6. **Serve** — the runtime where an agent loads a package, the two-tier BKM
   runs (thin skill → on-demand MCP), and real usage emits telemetry. The graph
   doubles as a **router** across a fleet of packaged experts. Design:
   [`serving.md`](serving.md).

## The feedback loop closes the cycle

A scorecard stamped once at build time goes stale. The loop makes it **living**
(design: [`feedback.md`](feedback.md)):

- **Serve → Measure.** Real questions and observed failures from production
  become new golden questions in the existing `personas`/`questions` track;
  re-scoring keeps the credential current.
- **Upstream-docs → Package.** The static `freshness_lite` signal marks a
  package's scorecard *stale* when a library's docs change, triggering CI
  re-evaluation and re-packaging.
- **Telemetry → Author.** Where agents loop, mis-trigger a skill, or work around
  a gap tells the authoring track what to distill or fix next.

## Key idea: AgentConfig is already a package

`agent-benchmark`'s `Treatment` → `AgentConfig` abstraction
(`../agent-benchmark/agent_benchmarks/treatments/base.py`) is
`system_prompt + skills + tools + injected_context` — which is exactly a
shippable agent. Packaging is largely *serializing and adapting* this existing
representation, not inventing a new one.

## Cross-cutting: attestation (the trust layer)

The scorecard threads through package → discover → feedback, so its
*trustworthiness* is a cross-cutting concern, not a single track. The scorecard
becomes a **signed, reproducible credential** any consumer — including a
third-party catalog — can verify without trusting us: the trust layer under any
listing, not just a better listing of our own. A deliberate strategic bet, later
than the core cycle. Design: [`attestation.md`](attestation.md).

## Open architectural questions

Tracked in the branch plan; to be resolved with design docs:

- Package manifest schema and how the scorecard is embedded.
- Which runtimes to target first and how their adapters differ.
- Graph technology and the intent/capability taxonomy.
- Whether to ship an Intel **MCP server** or only consume third-party ones
  (today `agent-benchmark` is an MCP *client*).
