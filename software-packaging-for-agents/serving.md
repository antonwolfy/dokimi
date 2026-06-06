# Design: the serve track — spawning an Intel expert on demand

> **Status:** DRAFT — for team review. Defines the *serve* track of the
> [architecture](architecture.md): where a packaged agent is actually used, and
> the loop closes by emitting telemetry. No code yet.
> **Date:** 2026-06-02

## 1. The product is a summonable expert

The persona is not just a system prompt buried inside a package — it is **what we
deliver**. The headline capability:

> Spawn an Intel expert for a specific Intel **software *or* hardware** product
> problem, pre-equipped with all the skills and MCP sources that expert needs.

A developer (or an orchestrating agent) describes a problem — "my oneMKL FFT
results drift between runs on Sapphire Rapids" — and gets back a *live expert
agent* already loaded with the right profile, the relevant skills, the right MCP
doc sources, and a verified environment. That is the unit of value, and it is
what makes the project a product rather than a benchmark.

This reframes the earlier tracks:

- **Package** produces the substrate (profile + skills + MCP + setup + scorecard).
- **Discover** finds the *right* substrate for a problem (capability graph).
- **Serve** turns that substrate into a running, scoped expert and watches it
  work.

## 2. Software *and* hardware experts

The catalog is not limited to oneAPI libraries. An Intel expert may be scoped to:

| Scope | Example expert | Where its value concentrates |
|---|---|---|
| **Software library** | oneTBB parallelism expert | API idioms, BKMs, pitfalls |
| **Numerical/accuracy** | oneMKL accuracy expert | fp reproducibility, conditioning, determinism flags |
| **Performance / optimization** | x86 perf-tuning expert (seed: [`intel/intel-performance-skills`](https://github.com/intel/intel-performance-skills)) | `perf` profiling, SIMD/AVX patterns, false sharing, fix playbooks |
| **Hardware platform** | Gaudi / Xeon-AMX / GPU-Max expert | hardware detection, tuning knobs, env config, known-good toolchains |
| **Cross-cutting problem** | "why is my HPC run non-deterministic?" | routes across several products (see §4) |

The optimization-expert row is not hypothetical: `intel/intel-performance-skills`
is a shipping, seed-shaped version of exactly that expert (composable `linux-perf`
→ `performance-patterns` → `phoronix-test-suite` skills). The serve track's job is
to wrap such a skill set in a problem-scoped persona, the right MCP sources, and a
[scorecard](packaging.md) so it can be *spawned by fit* rather than installed by
hand. Its skill-to-skill hand-off is also a concrete seed for the §4 router.

Hardware experts lean heavily on the **setup-guide** artifact (see
[`authoring.md`](authoring.md)): the expert's job is often to produce a
*working, tuned environment*, not just correct source. This is uniquely
Intel-shaped value a general model cannot fake.

## 3. What "spawn an expert" means concretely

A spawn request resolves a problem statement to a running agent:

```text
problem statement
   │
   ▼
DISCOVER: capability/intent graph → best-fit package(s)   (discovery.md)
   │
   ▼
ASSEMBLE: load package manifest → AgentConfig
          (profile = system prompt, skills, mcp refs, setup)
   │
   ▼
BKM at runtime: thin skill always loaded; MCP queried on demand   (packaging.md §3)
   │
   ▼
running expert  ──► answers / acts ──► emits telemetry   (feedback.md)
```

`AgentConfig` (`../doc-benchmark/doc_benchmarks/treatments/base.py`) is again the
in-memory shape: serving deserializes a package manifest back into an
`AgentConfig` and runs it through the same tool-calling loop
(`eval/agent_runner.py`) the benchmark already uses — the runtime and the
evaluator share one execution path, so what we *measure* is what we *serve*.

## 4. The graph as a router for a fleet of experts

For cross-cutting problems no single package covers, the discovery graph doubles
as a **router**: match the intent against capabilities, then either

- spawn the single best-fit expert, or
- compose a meta-expert that delegates sub-questions to specialist packages
  (`Package ──depends-on──►` / `bundles` edges already exist in
  [`discovery.md`](discovery.md)).

This is the bridge from "a catalog of packages" to "an on-demand Intel expert
for any problem."

## 5. Telemetry: the output that closes the loop

Serving is where the feedback arrow becomes real. Each session emits signal the
benchmark cannot synthesize (handled in [`feedback.md`](feedback.md)):

- the actual problem statement (a real question, not a persona-generated one),
- which skill(s) triggered and whether the MCP tier was reached for,
- where the agent looped, failed, or was corrected,
- the setup steps that did/didn't yield a working environment.

Privacy/telemetry policy is an open question (§7); the design assumes opt-in,
aggregated signal at minimum.

## 6. Delivery surfaces

"Spawn an expert" can surface in several ways, all consuming the same package:

- a runtime that loads the package as native Agent Skills / a Claude plugin (the
  exporters in [`packaging.md`](packaging.md));
- a hosted endpoint ("give me the oneMKL accuracy expert") backed by the graph;
- an MCP server that *is* the expert (see open question on shipping an Intel MCP
  server, [`packaging.md`](packaging.md) §7 / Q6).

## 7. Open questions

- **Spawn interface.** Library call, CLI (`expert spawn --problem "…"`), hosted
  service, or all three?
- **Composition policy.** When does the router spawn one expert vs compose
  several? How are conflicting answers reconciled?
- **Telemetry & privacy.** What is collected, where does it live, and what is the
  opt-in model — especially for customer/on-prem use?
- **Statefulness.** Is a spawned expert ephemeral per-problem, or a long-lived
  assistant that accumulates project context?

## 8. Relationship to the rest of the project

Serve sits downstream of [discover](discovery.md) and upstream of
[feedback](feedback.md). It is the track that makes the persona a *product* —
the others exist to make the spawned expert competent and trustworthy.
