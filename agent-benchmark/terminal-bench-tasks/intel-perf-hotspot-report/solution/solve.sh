#!/usr/bin/env bash
set -euo pipefail

cat > /app/hotspot_report.md <<'MD'
# Hotspot report for `solver --input case1`

Hotspot analysis was performed from the provided static `perf` artifacts.

## System-Level Summary

| Metric | Value | Interpretation |
| --- | ---: | --- |
| IPC | 0.61 | Low IPC: the CPU is not retiring much useful work per cycle. |
| Cache-miss rate | 1.07% | Low enough that the main `accumulate_scores` hotspot is not primarily memory-miss bound. |
| Branch-miss rate | 1.29% | Low enough that branch misprediction is not the main limiter. |
| Kernel time | 16.0% | Some kernel activity exists, but user-space functions dominate the profile. |

The workload is mostly CPU-bound. The top evidence points to a serial
accumulator in `accumulate_scores` plus false sharing in per-worker statistics.

## Top Functions

| Rank | Function | DSO | % |
| ---: | --- | --- | ---: |
| 1 | `accumulate_scores` | `solver` | 58% |
| 2 | `worker_update_stats` | `solver` | 19% |
| 3 | `__memmove_avx_unaligned_erms` | `libc.so.6` | 7% |
| 4 | `parse_record` | `solver` | 5% |
| 5 | `futex_wait_queue` | `[kernel]` | 2% |

## Annotated Hotspot: `accumulate_scores`

```c
      double accumulate_scores(const double *a, const double *b, size_t n)
      {
          double sum = 0.0;
          for (size_t i = 0; i < n; ++i) {
  76%         sum += a[i] * b[i];
          }
          return sum;
      }
```

Observation: this is a serial accumulator. The single `sum` variable creates a
loop-carried dependency, and the artifact shows scalar `vmulsd`/`vaddsd`
instructions on the dominant line.

## Cache-Line Contention Observation

`perf c2c` reports 17.8% total HITM in `worker_update_stats`. The access map
shows different threads writing different offsets (`0x00`, `0x08`, `0x10`,
`0x18`) on the same cache line.

Observation: this is false sharing. The threads are not logically sharing one
field; their independent per-worker counters are physically sharing one cache
line.

## Pattern Observations

- Pattern: serial accumulator. Evidence: `sum += a[i] * b[i]` accounts for 76%
  inside `accumulate_scores`, with low IPC and low cache/branch miss rates.
- Pattern: false sharing. Evidence: `perf c2c` HITM on one line with different
  thread-owned offsets in `worker_update_stats`.

This report names the observed patterns only. It does not claim that code was
changed or that a fix was applied.
MD
