# Intel Performance Skills Evaluation Plan

This plan covers the benchmark surface for
`intel/intel-performance-skills`. The question fixture measures awareness and
workflow selection. The executable task suite should measure whether the agent
can actually diagnose, change, rebuild, and verify performance work.

## Current Fixture

- `data/questions/intel_performance_skills_golden.json`
- 40 curated questions/tasks
- Coverage: `linux-perf`, `performance-patterns`, `phoronix-test-suite`
- Signal: workflow choice, evidence discipline, pattern classification,
  cross-skill handoff, and verification expectations

## Executable Tasks To Add

These should become terminal-bench style tasks. Each task needs a slow baseline,
tests for correctness, a performance gate, and an expected evidence trail.

| Task | Problem | Expected skill behavior | Verifier |
| --- | --- | --- | --- |
| `intel-perf-serial-accumulator` | scalar dot product / reduction bottleneck | detect serial accumulator, rewrite with independent accumulators or SIMD-safe reduction | numeric correctness + speedup threshold |
| `intel-perf-false-sharing` | per-thread fields share one cache line | use c2c/HITM reasoning, fix layout with padding/alignment | correctness + scaling improvement |
| `intel-perf-shared-counter` | global atomic statistics counter in hot path | classify true sharing, use per-thread/per-CPU aggregation | exact final count + throughput threshold |
| `intel-perf-ttas-spinlock` | TAS spinlock collapses at high thread count | identify `lock cmpxchg`, convert to TTAS | mutual exclusion correctness + scaling |
| `intel-perf-cv-herd` | worker pool wakes all threads per job | identify thundering herd, reduce unnecessary wakeups | job correctness + context-switch/throughput gate |
| `intel-perf-missing-restrict` | C array kernel blocked by alias checks | add valid `restrict` contract | output equality + vectorization/perf improvement |
| `intel-perf-vzeroupper` | AVX function returns to SSE caller | add `vzeroupper` at safe exits | output equality + assist counter/runtime improvement |
| `intel-perf-crc32c` | single-accumulator CRC32C | use optimized CRC32C with dispatch/fallback | known vectors + throughput threshold |
| `intel-perf-simd-sort` | `std::sort` over primitive numeric arrays | replace with SIMD sort where semantics allow | sortedness + stable-order non-requirement + speedup |
| `intel-perf-pts-lifecycle` | PTS benchmark optimization request | route through PTS lifecycle before perf/build | mocked PTS metadata/result files + report checks |

Start with synthetic C/C++ tasks for deterministic CI. Add real PTS tasks only
after the harness can tolerate long runtimes and machine variance.

## Broader Question Sources

Use several source families. Do not derive only from the skill README; that
overfits to capability recall.

1. Skill internals:
   `skills/linux-perf/references/*.md`,
   `skills/performance-patterns/triggers/*.md`,
   `skills/performance-patterns/patterns/*.md`,
   `skills/phoronix-test-suite/SKILL.md`.

2. Pattern microbenchmarks:
   small C/C++ programs for false sharing, atomics, locks, reductions, branch
   misses, cache misses, CRC32C, sort, and SIMD width.

3. Existing terminal-bench tasks:
   oneTBB, oneMKL, oneDPL, IPP tasks already in this repo can be adapted into
   performance-debug variants.

4. Phoronix Test Suite:
   CPU-bound tests such as compression, encode, math, crypto, sorting, and
   memory bandwidth tests can generate PTS lifecycle and score-direction cases.

5. Real profiler artifacts:
   sanitized `perf stat`, `perf report`, `perf annotate`, and `perf c2c` outputs
   from known workloads. These make questions test interpretation, not recall.

6. Open-source incident patterns:
   public issues and PRs involving scalability regressions, false sharing,
   lock contention, vectorization fixes, and dependency/library upgrades.

7. Intel and Linux performance references:
   Intel optimization manuals, Linux perf documentation, compiler
   vectorization reports, and PMU event references. Use these for edge cases
   and validation expectations, not for copying long text.

## Coverage Target

Minimum useful set:

- 60-80 awareness questions
- 8-10 executable tasks
- At least 3 question levels: triage, diagnosis, end-to-end
- At least 4 task types: source-only, profile-only, source+profile, PTS-style
- Explicit negative cases where the right answer is "do not optimize yet"

Difficulty and level are now two **independent, tagged axes** with a reproducible
rubric in [`difficulty-rubric.md`](difficulty-rubric.md). Every question carries
a top-level `level` field and negative cases carry `metadata.negative_case:
true`. The coverage target is to fill the `level × difficulty` grid (≥4-6 items
per cell), not to extend the current near-diagonal distribution. Report
evaluation lift sliced by that grid.

## Evaluation Rubric

Score answers separately on:

- workflow selection
- evidence gathered before diagnosis
- correct pattern classification
- safe operational behavior
- cross-skill handoff
- before/after verification
- benchmark score interpretation
- honesty about missing evidence

Do not blend the awareness score with executable task pass rate. They answer
different questions.
