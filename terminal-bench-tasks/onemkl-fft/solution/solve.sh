#!/usr/bin/env bash
set -euo pipefail

cat > /app/fft_mkl.c <<'CPP'
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include "mkl_dfti.h"

int main(int argc, char **argv) {
    int N = argc > 1 ? atoi(argv[1]) : 2048;
    if (N < 2) {
        fprintf(stderr, "INVALID_ARGUMENTS\n");
        return 2;
    }
    const double PI = 3.14159265358979323846;
    MKL_Complex16 *in = (MKL_Complex16 *)malloc(sizeof(MKL_Complex16) * N);
    MKL_Complex16 *out = (MKL_Complex16 *)malloc(sizeof(MKL_Complex16) * N);
    MKL_Complex16 *rec = (MKL_Complex16 *)malloc(sizeof(MKL_Complex16) * N);
    if (!in || !out || !rec) return 3;
    for (int i = 0; i < N; ++i) {
        in[i].real = cos(2.0 * PI * 5.0 * i / N) + 0.5 * sin(2.0 * PI * 12.0 * i / N);
        in[i].imag = 0.0;
    }

    DFTI_DESCRIPTOR_HANDLE h;
    DftiCreateDescriptor(&h, DFTI_DOUBLE, DFTI_COMPLEX, 1, (MKL_LONG)N);
    DftiSetValue(h, DFTI_PLACEMENT, DFTI_NOT_INPLACE);
    DftiCommitDescriptor(h);
    DftiComputeForward(h, in, out);

    double summag = 0.0, peakmag = -1.0;
    int peak = 0;
    for (int k = 0; k <= N / 2; ++k) {
        double mag = sqrt(out[k].real * out[k].real + out[k].imag * out[k].imag);
        summag += mag;
        if (k > 0 && mag > peakmag) { peakmag = mag; peak = k; }
    }

    DftiSetValue(h, DFTI_BACKWARD_SCALE, 1.0 / N);
    DftiCommitDescriptor(h);
    DftiComputeBackward(h, out, rec);

    double rterr = 0.0;
    for (int i = 0; i < N; ++i) {
        double d = fabs(rec[i].real - in[i].real);
        if (d > rterr) rterr = d;
    }
    DftiFreeDescriptor(&h);
    free(in); free(out); free(rec);
    printf("VALID fft peak=%d sig=%.6f rterr=%.3e\n", peak, summag, rterr);
    return 0;
}
CPP

gcc -O3 -std=c11 /app/fft_mkl.c -lmkl_rt -lpthread -lm -ldl -o /app/fft_mkl
