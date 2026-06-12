# Intel perf serial accumulator

You are given `/app/dot_serial.cpp`, a deterministic dot-product benchmark.
The included `/app/perf_stat.txt` shows low IPC with low cache and branch miss
rates, which points at a compute/dependency bottleneck rather than memory or I/O.

Create an optimized implementation that:

1. Computes the same dot product for the same optional CLI argument `<length>`.
2. Breaks the single loop-carried accumulator dependency using independent
   partial accumulators, threaded partial reductions, vector-friendly structure,
   or an equivalent safe reduction.
3. Writes source at `/app/dot_fast.cpp`.
4. Writes an executable binary at `/app/dot_fast`.
5. Prints a line containing `VALID dot=<value>`.

Do not change the mathematical input sequence. The verifier compares your
output with the serial reference and checks that it runs faster.

A typical compile command is:

```bash
g++ -O3 -std=c++17 -pthread /app/dot_fast.cpp -o /app/dot_fast
```
