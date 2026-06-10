# BACKLOG

## Active

---

### #59 — Evaluation beyond MCP docs: artifacts as subjects, model × harness, tasks for every project
**Scope:** Evaluation architecture / coverage
**Status:** PROPOSED

Extend the treatment-arm framework (#56) and the executable-task track so that
the things we actually want to ship — skills, agent profiles, bundles — are
**first-class evaluation subjects**, not just arms layered on a doc question; so
that **base model and agent harness** are explicit, swept dimensions (for coding
tasks they usually dominate the doc/skill delta); and so that **every project
carries both a question set (awareness) and a task set (work)**, not questions
alone.

Motivation, composition, and rollout order in the umbrella index
[docs/decisions/2026-06-10-evaluation-beyond-mcp-docs.md](docs/decisions/2026-06-10-evaluation-beyond-mcp-docs.md);
each phase is its own ADR (detailed design, alternatives, consequences, open
questions). Builds on the `treatments/` framework, `eval/arm_runner.py`, the
terminal-bench track, and feeds the packaging scorecard (#58d/#58i).

Phases (each independently shippable; existing `arms run` / two-arm doc flow stay
working):
- **Phase A — Coverage contract**
  ([ADR](docs/decisions/2026-06-10-questions-and-tasks-coverage-contract.md)).
  Per-product contract in config + a product × {questions, tasks} matrix in
  `terminal-bench-tasks/COVERAGE.md`; dashboard gains awareness vs work columns.
  Makes "text-only" products a visible TODO. No new eval machinery.
- **Phase B — Model × harness dimension**
  ([ADR](docs/decisions/2026-06-10-model-harness-dimension.md)). Promote answer
  model to a reported axis; name + record the harness (`single-shot` / `agent` /
  `terminal-bench:<agent>`); `matrix:` config block + `(model, harness)` key
  through `arm_runner`, report, dashboard; a `terminal-bench` harness adapter so
  task pass-rate is an arm outcome. Cost-gated, single-cell default.
- **Phase C — Subjects**
  ([ADR](docs/decisions/2026-06-10-artifacts-as-evaluation-subjects.md)).
  `subjects/` descriptor + loader, `cli.py subjects run` wrapping `arm_runner` +
  the task adapter, `report/subject_report.py`, and a versioned per-subject
  scorecard schema — the object #58d/#58i serialize/sign.

Each ADR carries its own open questions (harness invocation boundary,
subject-vs-package overlap, default matrix size, soft vs hard coverage
enforcement, …).

---

### #58 — Software-packaging-for-agents track (summonable Intel expert)
**Scope:** Project framing / packaging / discovery / serving
**Status:** FRAMING (docs landed; code deferred)

The repo became an umbrella monorepo: this benchmark moved under `doc-benchmark/`
and a new `software-packaging-for-agents/` track holds the framing. The
deliverable is a **summonable Intel expert** — spawn an expert for a specific
Intel software *or hardware* product problem, pre-equipped with the skills, MCP
sources, and setup guide it needs. Measurement (this project) is the **gate**,
not the product, and a feedback loop keeps each scorecard living.

The framing is a closed six-track cycle
(`../software-packaging-for-agents/architecture.md`):
**author → build → measure → package → discover → serve**, + feedback. Docs:
- `authoring.md` — distill skills from docs (benchmark as fitness function) +
  the executable, sandbox-verified setup-guide artifact.
- `packaging.md` — manifest (profile + skills + mcp + setup + scorecard),
  two-tier BKM (doc=skill → MCP on demand), per-runtime exporters.
- `discovery.md` — capability/intent graph + semantic search, ranked by vetted
  scorecard not popularity (the anti-"trending" design).
- `serving.md` — spawn a problem-scoped expert; graph as a fleet router; telemetry.
- `feedback.md` — telemetry + freshness re-score the scorecard (living credential).
- `attestation.md` — cross-cutting: the scorecard as a signed, portable credential
  third-party catalogs can verify (the trust layer, not just a better listing).

Sub-epics (code, deferred to follow-up PRs pending open questions Q3–Q6):
- **#58a — Agent-package builder.** Serialize `treatments/base.py` `AgentConfig`
  (+ a benchmark scorecard) into a `package.yaml` manifest; `package build` CLI.
- **#58b — Per-runtime exporters.** Anthropic Agent Skills layout first
  (`SKILL.md` already conforms), then Claude plugin, then Hermes/generic.
- **#58c — Discovery graph.** Consolidate `libraries.yaml` + `COVERAGE.md` +
  fixtures into one capability graph; fit-based + scorecard ranking.
- **#58d — Eval-scorecard-as-credential.** Wire `report/arms_report.py` output
  into the package manifest as the shipped, gating credential.
- **#58e — Skill distillation pipeline.** Doc→SKILL.md draft → score via
  `skill:`/`skill-agent:` arms → refine until the delta plateaus (authoring track).
  Also **ingest existing Intel skill repos** (e.g. `intel/intel-performance-skills`)
  as seed drafts + quality bar; score them and attach a scorecard so an
  already-shipping skill enters the cycle as a vetted, discoverable package.
- **#58f — Setup-guide artifact.** Executable env bootstrap verified on the
  terminal-bench track (Docker, `--network none`); first-class manifest field.
- **#58g — Serve / spawn-an-expert.** Deserialize a manifest → `AgentConfig` →
  `eval/agent_runner.py`; problem-scoped spawn; graph as router.
- **#58h — Feedback loop.** Telemetry → new golden questions → re-score;
  `freshness_lite` marks scorecards stale → CI re-evaluation.
- **#58i — Scorecard attestation (strategic, later).** Complete the scorecard
  provenance (reuse `artifacts.py` schema_version, `runner/manifest.py`,
  `question_set_hash`), make it reproducible-and-dated, then sign it so external
  catalogs can verify the claim without trusting us.

First proof package: `concise_expert` profile + `onetbb-quickstart` skill +
Context7 MCP for oneTBB — built entirely from existing fixtures.

---

### #57 — Productization hardening (external-review response)
**Scope:** Repo hygiene / contracts / packaging / CI
**Status:** DONE (P0–P2 landed)

Sequenced response to an external code-review. Full evaluation (claim-by-claim
verification + prioritized plan) in
[docs/decisions/2026-05-29-external-feedback-assessment.md](docs/decisions/2026-05-29-external-feedback-assessment.md).

- **P0 (trust & contracts) — DONE:** Apache-2.0 `LICENSE` + `NOTICE`,
  `SECURITY.md`, `CONTRIBUTING.md`, generic PR + issue templates; runtime
  `jsonschema` validation (`doc_benchmarks/runner/spec.py`, `schema_check`);
  `golden_manifest` include/exclude/min/max enforced in the runner; sandboxed
  example execution (`ExecutionPolicy`, default `backend=none`); LangChain-era
  quickstart fixed.
- **P1 (packaging & reproducibility) — DONE:** `pyproject.toml` + `doc-benchmark`
  entry point + extras; `requirements.lock.txt`; versioned artifact schemas +
  `schema_version` (`doc_benchmarks/artifacts.py`); `run_manifest`
  (`doc_benchmarks/runner/manifest.py`); CI lint/type/schema/drift + py
  3.10–3.13 matrix + package smoke (`.github/workflows/ci.yml`).
- **P2 (structure & breadth) — DONE:** `cli.py` split into `doc_benchmarks.cli`
  + `commands/`; product-registry drift detection (`config_check`); HF Datasets/
  JSONL/Parquet export (`dataset export`); deepened eval (grounding/citation
  metrics + bootstrap CIs, `eval grounding`); optional Docling ingestion
  (`ingest docling`); `CODEOWNERS`.

Follow-ups (deliberately deferred): broaden ruff (style/UP) and mypy coverage
across legacy modules; merge the two config files fully (currently
drift-checked); HF Hub publishing of exported datasets.

---

### #56 — Evaluate MCP docs, skills, and agent persona prompts
**Scope:** Evaluation architecture
**Status:** IN PROGRESS

Generalize the LLM track beyond the binary `with_docs`/`without_docs`
doc-injection experiment so it can measure the marginal value of three new
context-augmentation artifacts: MCP doc servers, agent skills, and agent
persona (system) prompts.

Assessment and phasing in
[docs/decisions/2026-05-29-evaluating-mcp-skills-personas.md](docs/decisions/2026-05-29-evaluating-mcp-skills-personas.md);
usage in [docs/evaluating-treatments.md](docs/evaluating-treatments.md).

Phases:
- **DONE** Phase 1 — agent persona prompts: `system` support in `llm.py`,
  `agent_profiles/` loader + fixtures, `AgentProfileTreatment`, N-arm
  `cli.py arms run` + report (the treatment-arm framework).
- **DONE** Phase 2 (injection) — MCP doc: `mcp/mcp_protocol.py` MCP-protocol
  client behind `factory.py` (`mcp:<ref>`), injected sub-arm. `mcp` SDK optional.
- **DONE** Phase 3 (in-process) — tool-calling agent loop
  (`eval/agent_runner.py`) with read-only tools: `agent[:source]` (doc search)
  and `skill-agent:<path>` (progressive disclosure); report records tool-use rate.
- **PARTIAL** Phase 4 — skills: `SKILL.md` loader, skill-as-context
  (`skill:`), and agentic skill-view (`skill-agent:`) arms done. Remaining:
  faithful skill *script execution*, which needs terminal-bench Docker
  isolation (the in-process loop is intentionally read-only).

Naming discipline (applied): `agent_profile`/`profile:` is the answerer's
system prompt; `persona` stays the synthetic-user concept.

---

### #54 — Executable tasks for non-TBB oneAPI components
**Scope:** Task generation / executable benchmarks
**Status:** IN REVIEW

Extend the terminal-bench task suite beyond oneTBB to the other Intel oneAPI
components, each with an offline-verifiable validation strategy (serial-reference
signature, analytic expected value, round-trip invariant, or drop-in comparison).

Added in this batch (verified per-task in the `terminal-bench-verify-oneapi`
matrix CI job, isolated from the core oneTBB job):

- `onemkl-dgemm` — `cblas_dgemm` vs serial triple-loop signature
- `onemkl-fft` — DFTI forward/backward round-trip + spectrum vs naive DFT
- `onedpl-transform-reduce` — `transform_reduce` (`par_unseq`) on the TBB backend
- `ipp-dotprod` — `ippsDotProd_64f` vs serial reference
- `sklearnex-classification` — `patch_sklearn()` KNN vs stock scikit-learn

Notes / follow-ups:
- `oneccl-allreduce` was prototyped but **removed from this batch**: oneCCL/Intel
  MPI transport under `--network none` needs iteration on a real image, which
  couldn't be done in the authoring sandbox (no nested Docker). Tracked as #55.
- Next candidates (per-component) tracked in `terminal-bench-tasks/COVERAGE.md`:
  oneMKL RNG/LAPACK/sparse, oneDPL sort/scan, oneDNN primitives, IPP image
  resize, IPP-CP AES, oneCCL allreduce/allgather/reduce, sklearnex kmeans/pca,
  OpenMP.

---

### #55 — oneCCL executable task (allreduce over MPI)
**Scope:** Task generation / executable benchmarks
**Status:** TODO

Land `oneccl-allreduce` (prototyped in #54, removed before merge). A multi-rank
sum allreduce verified against the analytic `N*(N+1)/2`. Needs to be iterated on
a real Docker image with oneCCL + Intel MPI working under `--network none`
(Intel MPI `shm` fabric, `CCL_ATL_TRANSPORT=mpi`, localhost in `/etc/hosts`,
`mpirun` bootstrap). Add to the `terminal-bench-verify-oneapi` matrix when green.

---

### #48 — Next oneTBB executable tasks: reduce, scan, flow graph
**Scope:** Task generation / executable benchmarks
**Status:** READY

Add the next three oneTBB terminal-bench-style tasks to cover core APIs that are not yet exercised by the current ParRes-inspired suite.

Tasks:
- `onetbb-parallel-reduce` — compute aggregate values over generated data with `oneapi::tbb::parallel_reduce`; verifier should compare against a serial reference and check source usage.
- `onetbb-parallel-scan` — implement prefix sums with `oneapi::tbb::parallel_scan`; verifier should validate exact prefix output/signature against serial reference.
- `onetbb-flow-graph` — build a small producer/transform/consumer graph with `oneapi::tbb::flow::graph`; verifier should validate deterministic output and graph API usage.

Deliverables:
- Docker environment, starter source, instruction, oracle `solution/solve.sh`, pytest verifier, `task.toml` for each task
- Offline oracle verification in CI with `--network none`
- README task table updates and coverage matrix entries
- Keep task sizes small enough for reliable CI, but strong enough to reject keyword-only or no-op solutions

---

### #49 — Repository structure and documentation cleanup
**Scope:** Repository hygiene / documentation
**Status:** PARTIAL

Initial pass: removed development-history markdown (STATUS*, PHASE_*, FINAL_*, TASK_*, IMPLEMENTATION_PLAN, NEXT_STEPS, MANUAL_TEST_PLAN, etc.), deleted unreferenced one-off scripts at repo root, dropped the legacy `benchmark.py` / `run_all_benchmarks.sh` pair (superseded by `cli.py` + `doc_benchmarks/`), moved `QUICKSTART.md` / `RUNBOOK.md` under `docs/`, and folded `generate_report.py` into `doc_benchmarks/report/eval_report.py`.

Still open:
- Add/refresh a contributor flow for adding terminal-bench tasks
- Add a oneTBB task coverage matrix: API/concept, task name, verifier type, difficulty, status
- Make Docker image naming and task metadata conventions explicit

---

### #47 — oneTBB executable task suite from ParRes Kernels
**Scope:** Task generation / executable benchmarks
**Status:** COMPLETED

Use https://github.com/ParRes/Kernels as a seed corpus for oneTBB tasks. The repo already contains simple Parallel Research Kernels with TBB implementations, which makes it a good base for terminal-bench style tasks that validate both documentation understanding and working oneTBB code.

Completed in PR #49:
- `onetbb-nstream` — memory bandwidth / parallel loop update
- `onetbb-stencil` — 2D neighborhood computation and boundary handling
- `onetbb-transpose` — blocked parallel transpose
- ParRes/Kernels provenance notes
- CI oracle verification for all included oneTBB tasks

Remaining ideas moved into future task candidates:
- `sparse` — sparse matrix-vector style workload
- `p2p` — point-to-point style communication pattern adapted to shared memory

---

### #30 — HTML dashboard
**Scope:** Reporting
**Status:** PLANNED

Static HTML file (Chart.js embedded) layered on top of the existing
`dashboard.json`.
- Bar chart per product
- Sortable / filterable table
- Drill-down on product click
- Generated by the same `dashboard generate --format html` command
- CI can publish it as an artifact

---

### #31 — Jenkins / CI pipeline
**Scope:** Automation
**Status:** PLANNED

Jenkinsfile for automatic benchmark runs.
- Parameterized run: library and model selection
- `benchmark batch --all` → `dashboard generate` → commit `DASHBOARD.md`
- Slack/Teams notification on score regression

---

### #32 — Real benchmark run: oneTBB + dashboard validation
**Scope:** Validation
**Status:** PLANNED

First real end-to-end run of the new pipeline:
- `benchmark run --library onetbb`
- Verify the dashboard is assembled from real data
- Lock in a baseline, compare against the previous one (Feb 25)

---

## Completed

- [x] PR #29 — Multi-evaluator LLM judge panel (3 roles, weighted aggregate, agreement score) (merged Feb 27, 2026)
- [x] PR #28 — Dashboard generate (`DASHBOARD.md` + JSON) (merged Feb 27, 2026)
- [x] PR #27 — Library registry (22 products) + benchmark run/batch (merged Feb 27, 2026)
- [x] PR #26 — Question quality analysis (merged Feb 27, 2026)
- [x] PR #25 — Arbitrary products (no GitHub repo required) + `--context7-id` (merged Feb 27, 2026)
- [x] PR #24 — Failure analysis / diagnose (merged Feb 26, 2026)
- [x] PR #23 — CodeRabbit follow-up fixes for PR #22 (merged Feb 26, 2026)
- [x] PR #22 — Multiple documentation sources (merged Feb 26, 2026)
- [x] PR #21 — CodeRabbit follow-up fixes (merged Feb 26, 2026)
- [x] PR #20 — Retry with backoff + baseline save/list/compare (merged Feb 26, 2026)
- [x] PR #19 — Parallel API calls via `ThreadPoolExecutor` (merged Feb 26, 2026)
- [x] PR #18 — Progress reporting + incremental saves + categories (merged Feb 26, 2026)
- [x] PR #17 — Drop LangChain, unify via LiteLLM (merged Feb 25, 2026)
- [x] First full oneTBB evaluation run (Feb 25, 2026) — baseline established
