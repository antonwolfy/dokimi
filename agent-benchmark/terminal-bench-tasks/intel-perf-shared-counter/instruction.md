# Intel perf shared counter

You are given `/app/shared_counter_bad.cpp`, a packet-processing style
benchmark. Every worker does useful deterministic work, then increments one
global atomic statistics counter in the hot path. The included
`/app/profile_excerpt.txt` shows `lock xadd`/true-sharing behavior.

Create a fixed implementation that:

1. Preserves the CLI: `<threads> <iterations>`.
2. Produces the same final total count and checksum.
3. Avoids one global atomic update per iteration; use per-thread/local
   aggregation and combine at the end.
4. Writes source at `/app/shared_counter_fixed.cpp`.
5. Writes an executable binary at `/app/shared_counter_fixed`.
6. Prints a line containing `VALID total=<value> checksum=<value>`.

A typical compile command is:

```bash
g++ -O3 -std=c++17 -pthread /app/shared_counter_fixed.cpp -o /app/shared_counter_fixed
```
