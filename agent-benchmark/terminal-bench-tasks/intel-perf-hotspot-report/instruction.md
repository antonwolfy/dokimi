# Intel perf hotspot report

You are given static profiling artifacts for `/app/solver`:

- `/app/perf_stat.txt`
- `/app/perf_report.txt`
- `/app/perf_annotate_accumulate.txt`
- `/app/perf_c2c.txt`

Create a structured Markdown hotspot report at `/app/hotspot_report.md`.

The report must:

1. Include a system-level summary that interprets IPC, cache misses, branch
   misses, and kernel time.
2. Include a top-functions table.
3. Include annotated-source or annotated-assembly evidence for the hot
   `accumulate_scores` function.
4. Include pattern observations based on the artifacts.
5. Correctly identify the serial accumulator signal.
6. Correctly identify the false-sharing/HITM signal.
7. Stay report-only: do not claim that you changed code or fixed the binary.

This is an artifact interpretation task, not a coding task.
