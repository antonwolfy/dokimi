# Design: the agent package format

> **Status:** DRAFT — for team review. Defines the *package*
> track of the [architecture](architecture.md). No code yet; this fixes the
> shape so the builder/exporters can be specced.
> **Date:** 2026-06-02

## 1. What we are packaging

An **agent package** is the distributable unit behind a [summonable Intel
expert](serving.md): the substrate that turns a general model into a domain
expert (e.g. an Intel HPC engineer, or a Gaudi/Xeon hardware expert) for a target
runtime. It bundles the artifacts from the architecture mainline —

> Intel expert persona → system prompt, skills, and MCP (+ setup guide).

— plus the provenance and the **evidence** that the bundle is worth installing.
The persona is the expert's *face*; the skills, MCP, and setup guide are what
make that expert actually competent.

The key observation: `agent-benchmark` already has the in-memory representation of
exactly this. A treatment's
[`AgentConfig`](../agent-benchmark/agent_benchmarks/treatments/base.py) is

```python
AgentConfig(
    system_prompt: str | None,        # the agent profile / persona
    injected_context: list[dict],     # docs / skill body
    tools: list[Tool],                # MCP doc search, skill view, …
    metadata: dict,                   # provenance
)
```

That is already an agent: *a persona, the knowledge it carries, and the
capabilities it can reach for*. **Packaging is serializing and adapting this
representation — not inventing a new one.** The benchmark builds `AgentConfig`s
to *score* treatments; the package track serializes the winning configuration to
*ship* it.

## 2. The manifest

A package is a directory with a `package.yaml` manifest plus the referenced
artifact files. Proposed schema (illustrative — to be locked with a JSON Schema
alongside `agent-benchmark`'s existing `benchmarks/spec.schema.json` convention):

```yaml
schema_version: 1
id: intel-onetbb-expert
name: Intel oneTBB Expert
description: >
  A senior C++ parallelism engineer specialised in Intel oneAPI Threading
  Building Blocks: parallel_for/reduce/scan, flow graph, concurrent containers.
version: 0.1.0
license: Apache-2.0

# ── The artifacts (the mainline) ─────────────────────────────────────────────
agent_profile: profiles/onetbb-expert.md      # → AgentConfig.system_prompt (the expert's face)
skills:                                        # → injected_context / skill tools
  - skills/onetbb-quickstart/SKILL.md
mcp:                                            # → on-demand doc retrieval (Tool)
  - ref: http=https://mcp.context7.com/mcp
    library_id: uxlfoundation/onetbb
    role: docs                                  # "ask the relevant part" tier
setup_guide: setup/onetbb-env.sh               # executable, sandbox-verified env bootstrap
                                                # (critical for hardware experts — see authoring.md)

# ── Provenance & evidence ───────────────────────────────────────────────────
provenance:
  source_libraries: [onetbb]                    # keys from products.yaml
  built_from: agent-benchmark@<git-sha>
scorecard:                                       # the shipped credential (§4)
  benchmark: agent-benchmark/arms
  question_set_hash: <sha>
  judge_model: <model>
  arms:
    baseline: 3.1
    this_package: 4.4
    delta: +1.3
  generated: 2026-06-02
```

Notes:
- `agent_profile`, `skills`, and `mcp` map **1:1** onto the existing loaders
  ([`load_agent_profile`](../agent-benchmark/agent_benchmarks/agent_profiles/loader.py),
  [`load_skill`](../agent-benchmark/agent_benchmarks/skills/loader.py)) and the
  `mcp:<ref>` doc source. Skill files already follow the Anthropic Agent Skills
  `SKILL.md` convention (frontmatter `name`/`description` + body), so they are
  portable as-is.
- `scorecard` is what makes this package *vetted* rather than merely *listed*
  (see §4). It is optional in the schema but strongly encouraged; the catalog
  ranks on it (see [discovery.md](discovery.md)).

## 3. The two-tier BKM (the load-bearing design principle)

From the brainstorm:

> documentation behaves as a general skill; MCP (or equivalent) is how the agent
> asks for the relevant part on demand.

This is the **prescribed shape** of an Intel agent package, not just one of
several options:

- **Tier 1 — the skill (always available, thin).** A compact `SKILL.md` that
  states *when to engage*, the canonical idioms, and the few pitfalls that
  actually matter. The committed
  [`onetbb-quickstart/SKILL.md`](../agent-benchmark/data/skills/onetbb-quickstart/SKILL.md)
  is exactly this shape: headers, the parallel-loop/reduce idioms, CMake wiring,
  and three pitfalls — nothing more.
- **Tier 2 — MCP (on-demand, thick).** The skill tells the agent *when* to reach
  for full documentation; the MCP doc source answers the specific question. The
  agent pays the token cost of detailed docs only when the skill says it's
  warranted.

`agent-benchmark` already measures both halves of this and can validate the
pattern empirically: the `skill-agent:` arm (progressive-disclosure skill view)
and the `agent:`/`mcp:` arms (on-demand doc retrieval) are precisely Tier 1 and
Tier 2 used agentically. Packaging *prescribes* the combination the benchmark
*validates*.

**Why this matters for packaging:** a package that inlines all documentation
into the prompt is expensive and dilutes attention; a package that ships only an
MCP reference has no always-on judgment about *when* to use it. The thin-skill +
on-demand-MCP pairing is the BKM the catalog should default to and reward.

## 4. Evidence as a first-class part of the package

The current `agent-benchmark` decision docs stop at *measuring* a treatment; they
never ask "how do we ship the winner?" This format closes that loop:

- The benchmark's per-arm report
  ([`report/arms_report.py`](../agent-benchmark/agent_benchmarks/report/arms_report.py))
  produces each arm's average judge score and its delta vs baseline.
- The package's `scorecard` block is a serialization of that result for *this*
  configuration.
- Distribution is **gated** on it: a package without a passing scorecard is a
  draft, not a release. This is the differentiator vs popularity-ranked
  marketplaces (cursor.directory et al.) — every Intel package carries the
  evidence that it measurably improves answers on a fixed question set.

This also gives the long-tail story teeth: a numerical-accuracy tool that will
never *trend* can still ship a strong, comparable scorecard, and the catalog can
rank on that instead of popularity (see discovery doc). Making that scorecard a
*signed, portable* credential a third-party catalog can verify is the
cross-cutting [attestation](attestation.md) design.

## 5. Per-runtime exporters

The manifest is runtime-neutral. Distribution happens through thin **adapters**
that translate it into each runtime's native layout. The manifest is the single
source of truth; adapters never add capability, only repackage it.

The **Agent Skills** target is the natural first exporter, and there is
real-world evidence it pays off: [`intel/intel-performance-skills`](https://github.com/intel/intel-performance-skills)
already distributes `SKILL.md` skills cross-runtime (Claude Code, Copilot, Codex,
Gemini CLI) via `gh skill install` from a single layout. One exporter, many
runtimes — so Agent Skills is the recommended first exporter target.

| Target | What the adapter emits | Notes |
|---|---|---|
| **Anthropic Agent Skills** | the `skills/` tree as-is + the profile as a system prompt | Closest to native; `SKILL.md` already conforms. Align with [intel/intel-performance-skills](https://github.com/intel/intel-performance-skills) layout (open question Q5). |
| **Claude plugin** | plugin manifest wrapping profile + skills + MCP server refs | Mirrors the existing intel-xpu-backend-for-triton Claude plugins. |
| **Hermes / generic** | system prompt + tool/MCP descriptors in a generic JSON bundle | For runtimes without a native skill concept. |

Proposed (future) CLI, living in the umbrella, reusing `agent-benchmark`'s loaders:

```bash
# Build a manifest from existing fixtures + a benchmark scorecard
package build --profile profiles/onetbb-expert.md \
              --skill skills/onetbb-quickstart \
              --mcp http=https://mcp.context7.com/mcp \
              --scorecard results/arms/oneTBB.json \
              --out packages/intel-onetbb-expert

# Export to a runtime
package export packages/intel-onetbb-expert --runtime claude
package export packages/intel-onetbb-expert --runtime agent-skills

# Register in the discovery catalog
catalog add packages/intel-onetbb-expert
```

## 6. The shipped-skill execution surface

`agent-benchmark` deliberately keeps in-process skills **read-only** — running a
skill's bundled scripts is pushed to the sandboxed terminal-bench track. A
*distributed* package can ship those bundled scripts (the `Skill.resources` the
loader already records but does not execute). So packaging reintroduces an
execution/security surface the eval side deferred. Requirements:

- The manifest must declare any bundled executables and their purpose.
- Provenance/licensing of bundled scripts is checked at `package build` time
  (mirror the terminal-bench `PROVENANCE.md` discipline).
- The catalog flags packages that ship executable resources so a consumer
  runtime can apply its own sandbox policy.

## 7. Open questions

- **Q5 — layout alignment.** Adopt `intel/intel-performance-skills`' existing
  package/skill layout, or define our own and provide an adapter to it?
- **Q6 — MCP server.** Do we ship an Intel **MCP doc server** (a new artifact
  with its own lifecycle), or only reference third-party ones (Context7)? Today
  `agent-benchmark` is purely an MCP *client*.
- **Manifest schema authority.** One schema for both `package.yaml` and the
  embedded scorecard, versioned like `benchmarks/spec.schema.json`?
- **Versioning.** How does a package version relate to the underlying library
  version and to the scorecard's question-set hash (re-score on doc changes)?

## 8. Relationship to `agent-benchmark`

| Package concept | Existing `agent-benchmark` piece |
|---|---|
| `agent_profile` | `data/agent_profiles/*.md` + `load_agent_profile` |
| `skills` | `data/skills/*/SKILL.md` + `load_skill` (+ `resources`) |
| `mcp` | `mcp:<ref>` doc source + `mcp/mcp_protocol.py` |
| in-memory bundle | `treatments/base.py` `AgentConfig` |
| `scorecard` | `report/arms_report.py` per-arm deltas |
| script execution | terminal-bench track (sandboxed) |

The first package to build is the obvious one: the `concise_expert` profile +
`onetbb-quickstart` skill + Context7 MCP for oneTBB — the fixtures already in the
repo become the first shipped Intel agent.
