# Intel perf SIMD / fast sort

You are given `/app/sort_bad.cpp`, which sorts a large array of `float` with
`std::sort`. The included `/app/perf_report.txt` shows the comparison sort
dominating runtime. Stable ordering is **not** required for this data.

Create a faster implementation that:

1. Preserves the CLI: optional `<length>`.
2. Preserves the deterministic input fill and the output contract: it must
   print `VALID sig=<value>` with the **same signature** as the reference
   (same sorted multiset) and the array must be fully sorted ascending.
3. Replaces `std::sort` on the hot path with a faster approach valid when
   stability is not required and the element type is a primitive — e.g. a
   vectorized sort (x86-simd-sort style) or a non-comparison radix sort over
   the float bit pattern.
4. Writes source at `/app/sort_fast.cpp`.
5. Writes an executable binary at `/app/sort_fast`.
6. Prints a line containing `VALID sig=<value>`.

A typical compile command is:

```bash
g++ -O3 -std=c++17 /app/sort_fast.cpp -o /app/sort_fast
```

The verifier checks the output is sorted, matches the reference signature
(same multiset), runs meaningfully faster, and does not just call `std::sort`
on the hot array.
