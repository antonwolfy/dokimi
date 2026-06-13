# Intel perf condition-variable thundering herd

You are given `/app/herd_bad.cpp`, a worker pool that calls `notify_all()` on
every submitted job. With a large pool, each single job wakes every worker;
all but one immediately go back to sleep. The included `/app/perf_sched.txt`
shows high context-switch and futex-wakeup counts that scale with pool size.

Create a fixed implementation that:

1. Preserves the CLI: `<workers> <njobs>`.
2. Preserves job semantics: every job processed **exactly once**; the final
   `processed` count equals `njobs` and `checksum` equals `njobs*(njobs+1)/2`.
3. Reduces unnecessary wakeups so a single enqueued job wakes a single worker
   (`notify_one`) rather than the whole pool, while still releasing all workers
   at shutdown.
4. Does not deadlock or lose wakeups.
5. Writes source at `/app/herd_fixed.cpp`.
6. Writes an executable binary at `/app/herd_fixed`.
7. Prints a line containing `VALID processed=<value> checksum=<value>`.

A typical compile command is:

```bash
g++ -O3 -std=c++17 -pthread /app/herd_fixed.cpp -o /app/herd_fixed
```

The verifier checks the exact processed count and checksum at several worker
counts, that the run terminates within the time limit (no deadlock/lost
wakeup), and that the per-job notify path is not `notify_all`.
