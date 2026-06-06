# oneMKL dense matrix multiply (cblas_dgemm)

You are given `/app/dgemm_serial.c`, a serial C reference that multiplies two
deterministic `N x N` double-precision matrices (`C = A * B`) with a naive triple
loop and prints a validation signature equal to the sum of all elements of `C`.

Create a oneMKL implementation that:

1. Generates the same matrices as the serial reference:
   `A[i,j] = ((i*7 + j*3) % 13) - 6` and `B[i,j] = ((i*5 + j*11) % 17) - 8`
   (row-major).
2. Computes `C = A * B` using `cblas_dgemm` from oneMKL (`#include "mkl.h"`).
3. Prints a line containing `VALID` and the same `sig=<value>` signature
   (sum of all elements of `C`).
4. Writes an executable binary at `/app/dgemm_mkl`.

Requirements:

- Use a real `cblas_dgemm` call, not a hand-written loop.
- Accept an optional CLI argument: `<N>` (matrix dimension).
- Reject `N < 1` with a non-zero exit code.

oneMKL is preinstalled. A typical compile command is:

```bash
gcc -O3 -std=c11 /app/dgemm_mkl.c -lmkl_rt -lpthread -lm -ldl -o /app/dgemm_mkl
```
