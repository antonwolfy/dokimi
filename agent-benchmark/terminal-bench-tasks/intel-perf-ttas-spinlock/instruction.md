# Intel perf TTAS spinlock

You are given `/app/spin_bad.cpp`, a contended-counter benchmark guarded by a
**test-and-set (TAS) spinlock**: each waiter loops on an atomic
`exchange`, so every spin writes the lock's cache line and the line bounces
between cores under contention. The included `/app/perf_annotate.txt` shows the
hot `lock ...` exchange instruction dominating the spin loop.

Create a fixed implementation that:

1. Preserves the CLI: `<threads> <iterations>`.
2. Preserves the exact final total (`threads * iterations`).
3. Converts the lock to a **test-and-test-and-set (TTAS)** design: spin on an
   ordinary (non-atomic-write) read of the flag and only attempt the atomic
   exchange once the flag looks free.
4. Writes source at `/app/spin_fixed.cpp`.
5. Writes an executable binary at `/app/spin_fixed`.
6. Prints a line containing `VALID count=<value>`.

A typical compile command is:

```bash
g++ -O3 -std=c++17 -pthread /app/spin_fixed.cpp -o /app/spin_fixed
```

The verifier checks that mutual exclusion still holds (exact total at several
thread counts), that the lock terminates well within the time limit at high
contention (no livelock), and that the source spins on an ordinary load before
the atomic exchange.
