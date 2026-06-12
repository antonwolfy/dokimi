# Design: the discovery layer (capability graph, not a trend ranking)

> **Status:** DRAFT — for team review. Defines the *discover*
> track of the [architecture](architecture.md). Tech-agnostic by intent;
> graph-DB and embedding choices are left open (Q4).
> **Date:** 2026-06-02

## 1. The problem: popularity ranking buries the catalog we care about

Agent-artifact marketplaces rank by popularity. The reference listing
([cursor.directory](https://cursor.directory/)) is, in the project's framing,

> "81.4k+ developers, ranked by what's trending."

That dynamic is structurally hostile to our catalog:

- Consumer-facing tools trend; **HPC libraries do not** trend among average
  developers.
- **Numerical-accuracy tools trend even less** — their audience is small,
  expert, and intermittent.

So the very artifacts this project exists to distribute — oneMKL FFT accuracy,
oneDAL, oneCCL, IPP — would sit permanently below the fold of a popularity-ranked
list. An agent searching by keyword or browsing "trending" will never reach
them. **Discovery cannot be popularity-based; it must be fit-based.**

> Numerical accuracy recurs here only as the sharpest *illustration* of
> valuable-but-un-trendy expertise — it motivates why ranking must be fit-based,
> not a capability this project commits to building or benchmarking.

## 2. The approach: a capability/intent graph with semantic search

Replace "what's trending" with "what *fits* this need." Two ingredients:

1. A **graph** whose edges express what each artifact *covers* and *depends on*,
   so a query can traverse from an expressed intent to the right package even
   when no keyword matches.
2. **Semantic (embedding) search** over capabilities and descriptions, so
   "I need a thread-safe parallel reduction in C++" resolves to the oneTBB
   `parallel_reduce` package without the word "reduction" appearing verbatim.

Ranking is then by **fit + vetted scorecard**, never by install count.

## 3. We already have most of the raw material

The repo holds the graph's seed data; today it is scattered across YAML and
Markdown tables rather than being one queryable structure.

| Graph element | Existing source in the repo |
|---|---|
| Library / product nodes | [`libraries.yaml`](../agent-benchmark/libraries.yaml) — 22 products with name, description, repo, doc sources, grouped by domain (Threading, Math & Numerics, …) |
| API / concept nodes + "task covers API" edges | [`terminal-bench-tasks/COVERAGE.md`](../agent-benchmark/terminal-bench-tasks/COVERAGE.md) — per-component API/concept → task → verifier matrix |
| Skill nodes + trigger hints | `data/skills/*/SKILL.md` frontmatter `description` (the trigger hint) |
| Agent-profile nodes | `data/agent_profiles/*.md` frontmatter `description` |
| Package nodes + scorecards | the [agent package format](packaging.md) manifests |
| Capability evidence | `report/arms_report.py` per-arm deltas |

This is closer to a knowledge graph than the current writing admits. The
discovery track's first job is to **consolidate these into one graph**, not to
collect new data.

## 4. Proposed schema

**Nodes**

- `Capability` / `Intent` — the spine. A normalized statement of *what an agent
  wants to do* ("parallel reduction over a large array in C++", "forward FFT
  with round-trip accuracy guarantees"). Independent of any product name.
- `Library` — from `libraries.yaml` (oneTBB, oneMKL, …).
- `API` / `Concept` — from `COVERAGE.md` (`parallel_reduce`, `cblas_dgemm`, `flow::graph`, …).
- `Skill`, `AgentProfile`, `MCPSource` — the package artifacts.
- `Package` — a shipped [agent package](packaging.md).
- `Task` — terminal-bench executable tasks (behavioral evidence).
- `Scorecard` — benchmark evidence attached to packages/treatments.

**Edges**

- `Skill ──covers──► Capability`
- `Capability ──realized-by──► API ──belongs-to──► Library`
- `Task ──exercises──► API` (from `COVERAGE.md`)
- `AgentProfile ──specializes-in──► Library`/`Capability`
- `Package ──bundles──► {AgentProfile, Skill, MCPSource}`
- `Package ──depends-on──► MCPSource`/`Library`
- `Package ──scored-by──► Scorecard`
- `Skill ──reaches-for──► MCPSource` (the two-tier BKM: Tier 1 → Tier 2)

## 5. Query model

An agent (or a router in front of a fleet of agents) queries by **intent**, not
keyword or trend:

1. Embed the intent; nearest-neighbor against `Capability`/`API`/description
   embeddings.
2. Traverse `Capability → realized-by → API → belongs-to → Library` and
   `Skill/Package → covers → Capability` to assemble candidate packages.
3. **Rank by fit × vetted evidence**: semantic similarity, capability-coverage
   completeness, and the package `Scorecard` delta — *not* popularity. A niche,
   never-installed numerical tool with a strong scorecard outranks a trendy
   package with none.
4. Return the package (and, per the BKM, its thin skill first; the MCP source is
   reached for on demand).

This is also the natural home for the **eval-scorecard-as-ranking-signal** idea:
the benchmark is what lets us rank on *demonstrated value* instead of crowd
behavior.

## 6. Build vs query (where embeddings come from)

`agent-benchmark` already declares an optional `embeddings` extra
(`sentence-transformers`, see `pyproject.toml`) used for chunk reranking. The
same dependency can embed capability/description text for the graph, so the
discovery layer does not introduce a new heavy dependency by default.

## 7. Scope boundary

- **In scope (design):** the schema, the seed-consolidation plan, the
  fit-based ranking model, and how the scorecard feeds ranking.
- **Out of scope (for now):** choosing the graph DB / vector store, building a
  UI, and federating with external catalogs. These are deliberately deferred.

## 8. Open questions

- **Q4 — graph & embedding stack.** Property graph (Neo4j-style) vs RDF/triples
  vs a lightweight in-repo graph (NetworkX + a vector index)? Reuse the existing
  `embeddings` extra, or a dedicated store? Kept open pending team decision.
- **Capability taxonomy.** Hand-curate the initial `Capability` vocabulary from
  `COVERAGE.md`, or derive it from doc/skill embeddings and cluster? Likely a
  seed-then-grow hybrid.
- **Re-scoring cadence.** A scorecard ages as docs/libraries change; how does the
  graph mark a scorecard stale and trigger re-evaluation?
- **External federation.** Do we expose this graph so other catalogs can ingest
  Intel packages, and/or ingest theirs?

## 9. Relationship to the rest of the project

The discovery layer sits downstream of [packaging](packaging.md): it
indexes packages and their scorecards. It is upstream of *use*: an agent hits the
graph to find the right package, installs it, and (per the BKM) loads the thin
skill, reaching for MCP on demand. The benchmark remains the authority that makes
the ranking trustworthy.
