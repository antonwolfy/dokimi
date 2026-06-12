# Intel Performance Skills Task Research

This research narrows the executable task plan for
`intel/intel-performance-skills`. The goal is to evaluate whether a skill-using
agent can solve performance work, not just answer questions about the skill.

## Evidence Sources

- Local task format: `terminal-bench-tasks/README.md` defines each task as
  `instruction.md`, `task.toml`, `environment/`, `tests/`, and `solution/`.
- Existing verifier style: `onetbb-nstream` checks a binary, compares with a
  serial reference, enforces a wall-time threshold, and inspects source markers.
- Skill repo evidence: `performance-patterns/patterns/tests/mutex-to-rwlock-*`
  contains a ready benchmark and measured before/after evidence for mutex versus
  rwlock behavior.
- Phoronix profiles: the public
  [`phoronix-test-suite/test-profiles`](https://github.com/phoronix-test-suite/test-profiles)
  repository contains PTS profile metadata and install scripts.
- Terminal-Bench reference:
  [`harbor-framework/terminal-bench`](https://github.com/harbor-framework/terminal-bench)
  and the Terminal-Bench paper describe tasks as Docker environments with
  instructions, tests, solution, and time limits.
- `perf c2c` references:
  [Red Hat false sharing guide](https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/8/html/monitoring_and_managing_system_status_and_performance/detecting-false-sharing_monitoring-and-managing-system-status-and-performance),
  [Linux kernel false sharing docs](https://docs.kernel.org/kernel-hacking/false-sharing.html),
  and [man7 perf-c2c](https://man7.org/linux/man-pages/man1/perf-c2c.1.html).

## Task Design Constraint

Do not require real privileged `perf` collection for the first CI suite. Perf
availability varies by kernel, container, PMU, host permissions, and
`perf_event_paranoid`. First-wave tasks should be deterministic C/C++ debugging
tasks with synthetic profile artifacts included as files. Later tasks can run
real `perf` only in a machine-profiled lane.

## Implemented First Wave

These are high-signal, low-flake tasks. They can run in Docker with offline
verification and no privileged PMU access.

| Priority | Task | What agent must do | Seed artifact | Verifier |
| --- | --- | --- | --- | --- |
| P0 | `intel-perf-serial-accumulator` | identify scalar reduction bottleneck and rewrite safely | slow dot product/reduction C++ file + sample `perf stat` | numeric equality + speedup threshold + source marker for multi-accumulator/vectorized structure |
| P0 | `intel-perf-false-sharing` | find adjacent per-thread counters and separate cache lines | multithreaded counter benchmark + synthetic `perf c2c` report | correct totals + speedup/scaling threshold + layout/alignment check |
| P0 | `intel-perf-shared-counter` | replace hot global atomic stat with local aggregation | packet/request counter benchmark + profile excerpt | exact final count + lower runtime threshold + no hot global atomic in source |
| P0 | `intel-perf-missing-restrict` | add valid C `restrict` contract to unlock vectorization | C array kernel + compiler/vectorization hint | output equality + `restrict` contract + vectorization evidence |
| P0 | `intel-perf-hotspot-report` | produce a structured report from provided perf artifacts | static `perf stat`, `perf report`, `perf annotate`, `perf c2c` files | markdown parser checks required sections and no unsupported fix claims |
| P1 | `intel-perf-ttas-spinlock` | convert TAS spinlock to TTAS | contended lock benchmark + annotate excerpt | mutual exclusion correctness + throughput improvement + ordinary-read spin path check |
| P1 | `intel-perf-mutex-rwlock` | replace read-mostly mutex with rwlock | adapt skill repo mutex-to-rwlock benchmark | correctness + read-heavy throughput improvement + write-path still works |
| P1 | `intel-perf-cv-herd` | reduce excessive condition-variable wakeups | worker-pool benchmark + futex/context-switch profile excerpt | all jobs processed exactly once + runtime/context-switch proxy improvement |
| P1 | `intel-perf-crc32c` | replace single-accumulator CRC32C with dispatched implementation | scalar/single-accumulator CRC32C | known vectors + throughput threshold + fallback path |
| P2 | `intel-perf-simd-sort` | replace primitive `std::sort` where stable order is not required | float/int sort workload | sortedness + no stability requirement + speedup threshold |

## PTS Task Research

PTS is valuable, but should be second wave because runtimes and downloads are
heavier. Good PTS tasks should verify lifecycle behavior, score semantics, and
source handling more than raw performance tuning.

| Candidate | Evidence | Fit | Risk |
| --- | --- | --- | --- |
| `pts/compress-zstd` | profile `compress-zstd-1.6.0` is HIB MB/s and builds `zstd-1.5.4` from source with `make -j`; wrapper runs `zstd -T$NUM_CPU_CORES` | good lifecycle/source rebuild case; useful threading and score-direction checks | external source/download size; score varies by host |
| `pts/openssl` | profile `openssl-3.3.0` is HIB and uses `openssl speed -multi $NUM_CPU_CORES` | good PTS install/run/parse task and CPU feature/library hotspot questions | crypto kernels already optimized; hard to create safe source edits |
| `pts/svt-av1` | profile `svt-av1-2.15.0` is HIB FPS, SMP-tagged, heavy encoder workload | realistic scaling/hotspot report task | large environment (~6900 MB), long runtime, not first wave |
| `pts/build-linux-kernel` | many versions available in profiles | good build-time benchmark and score parsing case | huge runtime; unsuitable for normal CI |

Recommended PTS first task: a mocked/minimized PTS lifecycle task. Provide local
profile-like metadata and a tiny source tarball that behaves like a PTS test.
The agent must read `install.sh`, preserve flags, rebuild with `-g`, parse HIB
metadata, run baseline/after, and report delta. This evaluates the skill's PTS
workflow without relying on OpenBenchmarking downloads.

## Real Perf Lane

After deterministic tasks pass, add an optional real-perf lane:

- requires Linux host with `perf` installed
- records `perf_event_paranoid` and PMU availability
- skips gracefully when hardware events/c2c are unavailable
- stores `perf stat`/`perf report` artifacts for later replay

Good real-perf candidates:

- false sharing with `perf c2c`
- TTAS spinlock with annotate evidence
- vzeroupper with `other_assists.avx_to_sse` where PMU supports it
- hotspot report generation from a short CPU-bound workload

## Broader Question Generation Sources

For a 60-80 question set, sample from these buckets:

| Bucket | Source | Question type |
| --- | --- | --- |
| Workflow routing | skill `SKILL.md` trigger sections | which skill/flow should run and why |
| Counter interpretation | `linux-perf/references/flow-a.md` plus synthetic stats | diagnose memory, branch, syscall, compute regimes |
| Profile artifacts | canned `perf report`, `annotate`, `c2c` outputs | classify pattern from evidence |
| Source smells | `performance-patterns/triggers/from-source.md` | detect patterns without profile data |
| Fix safety | pattern "Presenting this to the user" sections | when to ask, what ABI/semantic risks to mention |
| Benchmark semantics | PTS `test-definition.xml` files | HIB/LIB direction, TimesToRun, source/edit lifecycle |
| Existing tasks | current `terminal-bench-tasks/*` | turn oneAPI kernels into perf-debug variants |
| Public perf docs | Red Hat/kernel/man7 perf-c2c docs | c2c/HITM/false-sharing interpretation |

## Implementation Recommendation

The first five tasks have been implemented. Build remaining tasks in this order:

1. `intel-perf-ttas-spinlock`
2. `intel-perf-mutex-rwlock`
3. `intel-perf-cv-herd`
4. `intel-perf-crc32c`
5. `intel-perf-simd-sort`

The implemented first wave gives coverage across code rewrite, concurrency
scaling, compiler vectorization, and artifact/report interpretation while
keeping CI deterministic.
