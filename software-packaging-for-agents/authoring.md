# Design: the author track — manufacturing experts at scale

> **Status:** DRAFT — for team review. Defines the *author* track of the
> [architecture](architecture.md): how the skills, setup guides, and profiles
> that make an expert competent get produced for many products. No code yet.
> **Date:** 2026-06-02

## 1. The bottleneck

To [spawn an Intel expert](serving.md) for any product, that expert needs a thin
Tier-1 skill, the right MCP doc source, and — especially for hardware — a working
**setup guide**. Today the repo has exactly **one** hand-written skill
(`onetbb-quickstart`) and **one** profile (`concise_expert`). The catalog spans
22+ software libraries in [`products.yaml`](../agent-benchmark/products.yaml)
plus the hardware platforms (Gaudi, Xeon/AMX, GPU Max, NPUs). Hand-authoring does
not scale to that. Authoring must become a **pipeline**, with the benchmark as
its fitness function.

**Existing Intel skills are seeds, not noise.** Intel already publishes
hand-crafted skill collections in the Agent Skills format — e.g.
[`intel/intel-performance-skills`](https://github.com/intel/intel-performance-skills)
(`linux-perf` → `performance-patterns` → `phoronix-test-suite`). These are
high-quality, human-authored seeds: the authoring pipeline should **ingest** them
(as starting drafts and as the quality bar a distilled skill must match), score
them through the same arms as any other skill, and attach a [scorecard](packaging.md)
so an already-shipping skill enters the cycle as a vetted, discoverable package.
The pipeline augments expert authoring; it does not replace it.

## 2. Doc → skill distillation

Produce a candidate Tier-1 `SKILL.md` automatically, then *prove and refine* it:

```text
library docs / MCP source
   │  distill (LLM): when-to-engage + canonical idioms + top pitfalls
   ▼
candidate SKILL.md  ──►  MEASURE (agent-benchmark arms: skill: / skill-agent:)
   ▲                         │  judge delta + task pass-rate vs baseline
   │      refine             ▼
   └──────────────────  accept when the scorecard plateaus
```

- **Distill** targets the Tier-1 shape from [`packaging.md`](packaging.md) §3:
  compact, trigger-aware, idioms + the few pitfalls that matter — *not* a doc
  dump (the thick docs stay in the on-demand MCP tier).
- **Measure** reuses the existing arms machinery (`skill:` / `skill-agent:`
  treatments, `eval/arm_runner.py`) — no new evaluator. The candidate competes
  against `baseline`; a skill that doesn't move the score is rejected.
- **Refine** loops: feed low-scoring questions and judge rationales back into the
  next distillation pass until the delta stops improving.

Commit `78a6efe` already introduced an agentic loop for skills; this makes that
loop the **manufacturing line** — the benchmark stops being only a grader and
becomes the optimizer's objective function.

## 3. The setup-guide artifact (named in the brief, missing from the format)

For HPC and especially **hardware** experts, the agent-killer is not API usage —
it is the *environment*: compilers, oneAPI version pinning, MKL threading and
`KMP_AFFINITY`, hardware detection, fabric/driver setup. A package should carry an
executable **setup guide**: a bootstrap that, when run, yields a verified working
environment.

- It is a first-class artifact in the [package manifest](packaging.md), alongside
  `skills` and `mcp`.
- It is **verified by execution**, not by prose: the sandboxed terminal-bench
  track (`../agent-benchmark/terminal-bench-tasks/`, Docker + oracle + `--network
  none`) confirms the bootstrap produces a buildable/runnable environment. This
  is exactly where the deferred script-execution surface
  ([`packaging.md`](packaging.md) §6) earns its keep.
- Provenance/licensing of any bundled scripts is checked at author time, mirroring
  the terminal-bench `PROVENANCE.md` discipline.

A setup guide that is *proven* to produce a working Intel environment is value a
general model cannot fabricate — and the most reusable thing a hardware expert
can ship.

## 4. Profile authoring

Agent profiles (the persona system prompts) are short and high-leverage; they can
be authored per scope (per library, per hardware platform, per problem class) and
A/B'd as profile arms (`profile:`) against one another. The authoring track keeps
a small library of profile templates (e.g. a concise code-first expert, a
setup-and-tune specialist) that the build track composes with skills and MCP;
which templates exist is driven by what the [benchmark](../agent-benchmark/) and
real [feedback](feedback.md) show works, not fixed up front.

## 5. Human-in-the-loop

Distillation drafts; humans approve. The accept gate is the scorecard *plus* a
maintainer review — automated authoring proposes, the benchmark filters, a person
signs off before a package ships. This mirrors the repo's existing
persona/question *discover → approve* pattern.

## 6. Open questions

- **Distillation source of truth.** Distill from rendered docs, from the MCP
  source, or from the executable tasks (which encode known-good usage)?
- **Plateau criterion.** What scorecard-delta threshold and how many refine
  iterations before accept/reject?
- **Hardware coverage.** Which hardware platforms get experts first, and what is
  the verification environment for hardware-specific setup (real silicon vs
  emulation in CI)?
- **Reuse across scopes.** How much can one distilled skill serve multiple
  experts (shared Tier-1 skills referenced by several packages)?

## 7. Relationship to the rest of the project

Author is the head of the cycle: it feeds [build](architecture.md) and is in turn
fed by [feedback](feedback.md) (telemetry tells it what to distill or fix next).
The benchmark ([measure](../agent-benchmark/)) is its fitness function throughout.
