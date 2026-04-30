# Terminal-Bench Tasks for Intel oneAPI Libraries

This directory contains [Terminal-Bench](https://github.com/laude-institute/terminal-bench) /
[Harbor](https://github.com/laude-institute/harbor) tasks for evaluating LLM coding agents
on Intel oneAPI libraries (oneTBB, oneMKL, oneCCL, IPP, etc.).

## Why Terminal-Bench?

Unlike pure Q&A benchmarks, Terminal-Bench tasks require the agent to:
- Write real C++ / Python code using Intel libraries
- Compile and run it in an isolated Docker environment
- Pass automated correctness **and** performance tests

This complements the existing `eval/` Q&A benchmark with **coding-task evaluation**.

## Task Structure

Each task follows the [Harbor task format](https://harborframework.com/docs/tasks):

```text
terminal-bench-tasks/<task-name>/
  instruction.md          # Natural-language task description shown to the agent
  task.toml               # Config: timeouts, Docker image, metadata
  environment/
    Dockerfile            # Container with preinstalled libs
    <seed files>          # Starter code, data files, etc.
  tests/
    test.sh               # Entry point: runs pytest, writes /logs/verifier/reward.txt
    test_*.py             # Pytest test cases
  solution/
    solve.sh              # Oracle solution (sanity check, not shown to agent)
```

## Available Tasks

See [COVERAGE.md](./COVERAGE.md) for the broader oneTBB API/concept coverage matrix and planned gaps.

| Task | Library | Difficulty | What it tests |
|------|---------|------------|---------------|
| [onetbb-parallel-sort](./onetbb-parallel-sort/) | oneTBB | medium | `tbb::parallel_sort` on 10M integers; correctness + ≤5s wall time |
| [onetbb-nstream](./onetbb-nstream/) | oneTBB | medium | ParRes-inspired streaming triad with `parallel_for` + `parallel_reduce` |
| [onetbb-stencil](./onetbb-stencil/) | oneTBB | medium | ParRes-inspired 2D stencil with tiled `blocked_range2d` parallelism |
| [onetbb-transpose](./onetbb-transpose/) | oneTBB | medium | ParRes-inspired tiled matrix transpose with `blocked_range2d` |

## Running a Task (Harbor)

```bash
pip install harbor-cli   # or: uv tool install harbor-cli

# Evaluate an agent on a single task
harbor run \
  -p terminal-bench-tasks/onetbb-parallel-sort \
  -a terminus \
  -m anthropic/claude-opus-4-6

# Use the Oracle agent to sanity-check the solution
harbor run \
  -p terminal-bench-tasks/onetbb-parallel-sort \
  -a oracle
```

## Provenance

The ParRes-inspired tasks are simplified exercises derived from the ideas in [ParRes/Kernels](https://github.com/ParRes/Kernels), not verbatim copies of upstream source files. See [PROVENANCE.md](./PROVENANCE.md) for details and license notes.

## Docker Images

Tasks use custom Docker images built from `environment/Dockerfile`.
To build locally:

```bash
docker build -t intel-hpc-bench/onetbb-parallel-sort:latest \
  terminal-bench-tasks/onetbb-parallel-sort/environment/
docker build -t intel-hpc-bench/onetbb-nstream:latest \
  terminal-bench-tasks/onetbb-nstream/environment/
```

## Adding New Tasks

1. Pick an API/concept gap from [COVERAGE.md](./COVERAGE.md).
2. Copy an existing task folder as a template.
3. Update `instruction.md`, `task.toml`, `environment/Dockerfile`, and starter sources.
4. Write tests in `tests/test_*.py` — they must write `1` or `0` to `/logs/verifier/reward.txt` via `tests/test.sh`.
5. Add a deterministic oracle solution in `solution/solve.sh`.
6. Build the Docker image and smoke-test the oracle verifier offline with `--network none`.
7. Add a row to the table above and update the coverage matrix.

## Roadmap

- [ ] `onetbb-parallel-reduce` — compute sum/max with `tbb::parallel_reduce`
- [ ] `onetbb-flow-graph` — producer-consumer pipeline with `tbb::flow::graph`
- [ ] `onemkl-dgemm` — matrix multiplication via cblas_dgemm, verify GFLOPS
- [ ] `onemkl-fft` — FFT round-trip via DFTI
- [ ] `oneccl-allreduce` — multi-process allreduce with oneCCL + MPI
- [ ] `ipp-image-resize` — image resize with ippiResize, verify pixel accuracy
