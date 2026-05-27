# oneTBB executable task coverage

This matrix tracks which oneTBB APIs and concepts are covered by terminal-bench-style coding tasks.

| API / concept | Task | Status | Verifier strategy |
| --- | --- | --- | --- |
| `parallel_sort` | `onetbb-parallel-sort` | merged | Sort correctness, runtime bound, source marker checks |
| `parallel_for` + `parallel_reduce` | `onetbb-nstream` | merged | Serial checksum comparison, source marker checks |
| `blocked_range2d` stencil update | `onetbb-stencil` | merged | Serial norm comparison, source marker checks |
| `blocked_range2d` transpose | `onetbb-transpose` | merged | Serial probe-signature comparison, source marker checks |
| `parallel_reduce` | `onetbb-parallel-reduce` | implemented | Serial aggregate comparison, source marker checks |
| `parallel_scan` | `onetbb-parallel-scan` | implemented | Serial prefix signature comparison, source marker checks |
| `flow::graph` | `onetbb-flow-graph` | implemented | Deterministic graph output comparison, graph API checks |
| `task_group` | TBD | candidate | Dependency/task execution validation |
| `concurrent_hash_map` | TBD | candidate | Concurrent update correctness and source API checks |
| `task_arena` / `global_control` | TBD | candidate | Thread-limit behavior and source API checks |

## Notes for new tasks

Prefer deterministic, small workloads that can be verified offline in CI. Each task should have a serial reference or independently computed expected result so verifiers reject keyword-only implementations. Runtime thresholds should be conservative enough to avoid flaky CI while still detecting obviously inefficient or non-terminating solutions.
