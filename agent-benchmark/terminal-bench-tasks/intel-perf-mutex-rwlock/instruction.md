# Intel perf mutex to rwlock

You are given `/app/rwlock_bad.cpp`, a read-mostly shared table guarded by a
plain `std::mutex`. About 99.9% of operations are pure reads, but the mutex
serializes readers against each other. The included `/app/perf_report.txt`
shows lock-wait time dominating.

Create a fixed implementation that:

1. Preserves the CLI: `<threads> <ops>`.
2. Preserves correctness: the final array checksum must equal the reference's
   for the same arguments (writes are not lost, reads do not mutate state).
3. Replaces the plain mutex with a reader-writer lock so readers share access
   (`std::shared_lock<std::shared_mutex>`) and writers remain exclusive
   (`std::unique_lock<std::shared_mutex>`).
4. Writes source at `/app/rwlock_fixed.cpp`.
5. Writes an executable binary at `/app/rwlock_fixed`.
6. Prints a line containing `VALID checksum=<value> reads=<value>`.

A typical compile command is:

```bash
g++ -O3 -std=c++17 -pthread /app/rwlock_fixed.cpp -o /app/rwlock_fixed
```

The verifier checks the checksum matches the reference at several thread counts
(write path still correct), that the run terminates within the time limit, and
that the source uses a shared/reader-writer lock for the read path.
