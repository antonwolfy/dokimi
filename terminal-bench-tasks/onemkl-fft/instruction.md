# oneMKL FFT round-trip (DFTI)

You are given `/app/fft_serial.c`, a serial C reference that computes the
magnitude spectrum of a deterministic length-`N` signal with a naive DFT and
prints the dominant non-DC bin (`peak`) and the sum of magnitudes (`sig`).

Create a oneMKL implementation that:

1. Builds the same signal: `x[i] = cos(2*pi*5*i/N) + 0.5*sin(2*pi*12*i/N)`.
2. Uses the oneMKL **DFTI** interface (`#include "mkl_dfti.h"`) to compute the
   forward FFT, then the backward FFT.
3. Reports `peak=<k>` (dominant non-DC bin) and `sig=<sum-of-magnitudes>` that
   match the serial reference, plus `rterr=<max-roundtrip-error>` where the
   backward transform (scaled by `1/N`) recovers the original input.
4. Prints a line containing `VALID` with those values.
5. Writes an executable binary at `/app/fft_mkl`.

Requirements:

- Use real `DftiCreateDescriptor` / `DftiComputeForward` / `DftiComputeBackward`
  calls, not a hand-written DFT.
- The round-trip error must be tiny (well under `1e-6`).
- Accept an optional CLI argument: `<N>`.

oneMKL is preinstalled. A typical compile command is:

```bash
gcc -O3 -std=c11 /app/fft_mkl.c -lmkl_rt -lpthread -lm -ldl -o /app/fft_mkl
```
