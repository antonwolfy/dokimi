# oneDPL parallel transform-reduce

You are given `/app/reduce_serial.cpp`, a serial C++ reference that builds a
deterministic sequence `v[i] = ((i*17 + 13) % 1009) - 504` and computes the sum
of squares as a validation signature.

Create a oneDPL implementation that:

1. Generates the same sequence.
2. Uses `oneapi::dpl::transform_reduce` with a parallel execution policy
   (`oneapi::dpl::execution::par_unseq`) to compute the sum of squares.
   Include `<oneapi/dpl/execution>` and `<oneapi/dpl/numeric>`.
3. Prints a line containing `VALID` and the same `sig=<value>` signature.
4. Writes an executable binary at `/app/dpl_reduce`.

Requirements:

- Use a real oneDPL parallel algorithm with a parallel policy, not a serial loop.
- Accept an optional CLI argument: `<length>`.
- Reject zero-length inputs with a non-zero exit code.

oneDPL and oneTBB are preinstalled. A typical compile command is:

```bash
g++ -O3 -std=c++17 /app/dpl_reduce.cpp -ltbb -pthread -o /app/dpl_reduce
```
