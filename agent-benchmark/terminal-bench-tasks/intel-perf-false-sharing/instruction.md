# Intel perf false sharing

You are given `/app/false_sharing_bad.cpp`, a multithreaded counter benchmark.
Each worker updates only its own counter, but the counters sit on the same cache
line. The included `/app/perf_c2c.txt` shows HITM traffic at different byte
offsets, which is the classic false-sharing signature.

Create a fixed implementation that:

1. Preserves the same CLI: `<threads> <iterations>`.
2. Preserves the same final total.
3. Separates per-thread counters onto independent cache lines using alignment,
   padding, or an equivalent layout fix.
4. Writes source at `/app/false_sharing_fixed.cpp`.
5. Writes an executable binary at `/app/false_sharing_fixed`.
6. Prints a line containing `VALID total=<value>`.

A typical compile command is:

```bash
g++ -O3 -std=c++17 -pthread /app/false_sharing_fixed.cpp -o /app/false_sharing_fixed
```
