# Intel IPP vector dot product (ippsDotProd)

You are given `/app/ipp_serial.c`, a serial C reference that builds two
deterministic vectors and computes their dot product as a validation signature:
`a[i] = ((i*7 + 1) % 101) - 50`, `b[i] = ((i*13 + 3) % 97) - 48`.

Create an Intel IPP implementation that:

1. Generates the same two vectors as `Ipp64f` (double) arrays.
2. Computes the dot product using `ippsDotProd_64f` (`#include <ipp.h>`).
3. Prints a line containing `VALID` and the same `dot=<value>` signature.
4. Writes an executable binary at `/app/ipp_dot`.

Requirements:

- Use a real `ippsDotProd_64f` call, not a hand-written loop.
- Accept an optional CLI argument: `<length>`.
- Reject `length < 1` with a non-zero exit code.

Intel IPP is preinstalled. A typical compile command is:

```bash
gcc -O3 -std=c11 /app/ipp_dot.c -lipps -lippcore -lm -o /app/ipp_dot
```
