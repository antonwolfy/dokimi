# Next Steps

Current focus: make `doc-benchmark` useful for both documentation-quality analysis and executable coding-task evaluation.

## Priority 1 — Add next three oneTBB executable tasks

Create a focused PR with these tasks:

1. `onetbb-parallel-reduce`
   - API focus: `oneapi::tbb::parallel_reduce`
   - Workload: deterministic aggregate over generated numeric data
   - Verifier: serial reference comparison, runtime bound, source marker checks

2. `onetbb-parallel-scan`
   - API focus: `oneapi::tbb::parallel_scan`
   - Workload: prefix sum / cumulative transform
   - Verifier: exact output signature against serial reference, source marker checks

3. `onetbb-flow-graph`
   - API focus: `oneapi::tbb::flow::graph`
   - Workload: deterministic producer → transform → consumer graph
   - Verifier: validates final output and graph API usage, not just keywords

All tasks should follow the existing terminal-bench task shape: `instruction.md`, `task.toml`, `environment/`, `solution/`, and `tests/`. CI verification must run offline with `--network none`.

## Priority 2 — Repository structure and documentation cleanup

Do a cleanup PR after or alongside the next task batch if it stays small.

Goals:

- Make the top-level README a concise map of the project, not a dumping ground.
- Add or refresh docs for the two workflows:
  - static docs-quality benchmarking
  - terminal-bench-style executable tasks
- Add a oneTBB task coverage matrix showing API/concept coverage.
- Reconcile stale planning files (`BACKLOG.md`, `NEXT_STEPS.md`, `STATUS*.md`) so they match current `main`.
- Document Docker image naming and offline verifier requirements.

## Suggested workflow for future task work

1. Pick an API/concept gap from the coverage matrix.
2. Define a small deterministic workload and a serial reference.
3. Write the task instruction with exact I/O and validation semantics.
4. Implement oracle solution using the required oneTBB API.
5. Write pytest verifier that checks correctness, source usage, and basic runtime.
6. Run local Docker oracle verification with `--network none`.
7. Add the task to CI and README/coverage matrix.
8. Open PR, address review comments, merge only when checks are green.
