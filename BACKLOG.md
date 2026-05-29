# BACKLOG

## Active

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
