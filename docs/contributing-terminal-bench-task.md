# Adding a terminal-bench task

Tasks under `terminal-bench-tasks/` evaluate LLM coding agents on real Intel
oneAPI workloads: the agent gets an `instruction.md` and an environment, has
to produce working code, and is graded by pytest inside a Docker sandbox.

CI builds each task's container and runs the oracle solution offline to make
sure the task is solvable and the verifier rejects obvious no-ops.

This guide covers the contributor flow. The format reference lives in
`terminal-bench-tasks/README.md`; the coverage matrix is in
`terminal-bench-tasks/COVERAGE.md`.

## 1 — Pick a task

Aim for one focused API or concept per task. Good candidates currently come
from [`BACKLOG.md`](../BACKLOG.md) item #48 and the gaps listed in
[COVERAGE.md](../terminal-bench-tasks/COVERAGE.md). When adapting external
code, record the source in
[PROVENANCE.md](../terminal-bench-tasks/PROVENANCE.md) and confirm the
license allows redistribution.

A task should:

- Exercise a single primary API (`parallel_for`, `parallel_reduce`,
  `flow::graph`, …) plus minimal scaffolding.
- Be small enough to compile and run reliably under CI's `--network none`
  sandbox in well under the configured `verifier.timeout_sec`.
- Be strong enough to reject keyword-only or no-op solutions — the verifier
  must check observable behavior, not just file presence or comment
  patterns.

## 2 — Lay out the directory

```text
terminal-bench-tasks/onetbb-<name>/
  instruction.md          # task description shown to the agent
  task.toml               # config: timeouts, Docker image, metadata
  environment/
    Dockerfile            # base image + preinstalled libs
    <seed files>          # starter source, headers, data
  tests/
    test.sh               # entry point; writes /logs/verifier/reward.txt
    test_*.py             # pytest cases
  solution/
    solve.sh              # oracle solution (not shown to the agent)
```

Use an existing task as a template, e.g. `onetbb-nstream/` for compute
kernels or `onetbb-flow-graph/` for pipelines.

## 3 — Naming and metadata conventions

- Directory name: `onetbb-<concept>` (lower-kebab-case). Use the library
  prefix that matches the primary API surface (`onemkl-…`, `onednn-…`).
- `task.toml` fields:
  - `metadata.difficulty` — `easy` / `medium` / `hard`.
  - `metadata.category` — usually `programming`.
  - `metadata.tags` — include the library (`onetbb`), the concept
    (`parallel-reduce`), and any provenance tag (`parres`).
  - `verifier.timeout_sec` — keep ≤ 60s for CI.
  - `agent.timeout_sec` — typically 300s.
  - `environment.docker_image` — `intel-hpc-bench/<task-name>:latest`.
  - `environment.allow_internet = false` for CI parity.

## 4 — Verifier requirements

The verifier (`tests/test.sh` + `tests/test_*.py`) must:

- Compile the agent's submitted source from a stable path (mirror the
  pattern in existing tasks).
- Run it with deterministic input (fixed seeds; no wall-clock-dependent
  output unless explicitly part of the task).
- Compare output against a serial reference computed in the test itself —
  do not check the agent's source for substrings as the only signal.
- Check at least one structural signal too (e.g., the source uses
  `tbb::parallel_reduce`) so a serial submission that produces the right
  answer is still rejected.
- Write the pytest result into `/logs/verifier/reward.txt` (`1.0` pass /
  `0.0` fail), matching the Harbor convention.

## 5 — Oracle solution

`solution/solve.sh` must produce a passing run end-to-end. It is invoked by
CI with no network and must rely solely on the image and seed files. Keep
it minimal — the oracle is a correctness baseline, not a tutorial.

## 6 — Local verification

```bash
# Build the image
docker build -t intel-hpc-bench/onetbb-<name>:latest \
  terminal-bench-tasks/onetbb-<name>/environment

# Run the oracle offline (mirrors CI)
docker run --rm --network none \
  -v "$PWD/terminal-bench-tasks/onetbb-<name>:/task" \
  intel-hpc-bench/onetbb-<name>:latest \
  bash -c "cp /task/solution/solve.sh /tmp/solve.sh && \
           bash /tmp/solve.sh && \
           bash /task/tests/test.sh && \
           cat /logs/verifier/reward.txt"
```

Expected output: `1.0`.

Negative check — confirm the verifier rejects a no-op:

```bash
docker run --rm --network none \
  -v "$PWD/terminal-bench-tasks/onetbb-<name>:/task" \
  intel-hpc-bench/onetbb-<name>:latest \
  bash -c "bash /task/tests/test.sh; cat /logs/verifier/reward.txt"
```

Expected output: `0.0`.

## 7 — Register the task

- Add a row to the table in
  [`terminal-bench-tasks/README.md`](../terminal-bench-tasks/README.md).
- Add an entry to
  [`terminal-bench-tasks/COVERAGE.md`](../terminal-bench-tasks/COVERAGE.md)
  with API/concept, verifier type, difficulty, and status.
- If the task is adapted from an external source, record the upstream
  commit, license, and any modifications in
  [`terminal-bench-tasks/PROVENANCE.md`](../terminal-bench-tasks/PROVENANCE.md).

## 8 — CI

The `Verify terminal-bench-tasks` workflow picks up new directories
automatically. Confirm the green run on your PR before requesting review.
