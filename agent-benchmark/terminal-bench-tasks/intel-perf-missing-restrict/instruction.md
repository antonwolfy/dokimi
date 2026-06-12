# Intel perf missing restrict

You are given `/app/saxpy_aliasing.c`, a C array kernel. The caller contract
guarantees that `x`, `y`, and `out` never overlap, but the function signature
does not say that. The included `/app/annotate_aliasing.txt` shows an aliasing
preamble and scalar fallback.

Create a fixed implementation that:

1. Uses a valid C `restrict` contract on the non-overlapping pointer parameters.
2. Preserves the CLI: `<length> <iterations>`.
3. Produces the same checksum as the reference.
4. Writes source at `/app/saxpy_restrict.c`.
5. Writes an executable binary at `/app/saxpy_restrict`.
6. Prints a line containing `VALID checksum=<value>`.

A typical compile command is:

```bash
gcc -O3 -std=c11 /app/saxpy_restrict.c -lm -o /app/saxpy_restrict
```
