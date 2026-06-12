#!/usr/bin/env bash
set -euo pipefail

cat > /app/dgemm_mkl.c <<'CPP'
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "mkl.h"

static double av(int i, int j) { return (double)(((i * 7 + j * 3) % 13) - 6); }
static double bv(int i, int j) { return (double)(((i * 5 + j * 11) % 17) - 8); }

int main(int argc, char **argv) {
    int N = argc > 1 ? atoi(argv[1]) : 640;
    if (N < 1) {
        fprintf(stderr, "INVALID_ARGUMENTS\n");
        return 2;
    }
    /* Reject sizes where N*N*sizeof(double) would overflow size_t. */
    size_t n = (size_t)N;
    if (n > SIZE_MAX / n || n * n > SIZE_MAX / sizeof(double)) {
        fprintf(stderr, "INVALID_ARGUMENTS\n");
        return 2;
    }
    double *A = (double *)mkl_malloc(sizeof(double) * (size_t)N * N, 64);
    double *B = (double *)mkl_malloc(sizeof(double) * (size_t)N * N, 64);
    double *C = (double *)mkl_calloc((size_t)N * N, sizeof(double), 64);
    if (!A || !B || !C) return 3;

    for (int i = 0; i < N; ++i)
        for (int j = 0; j < N; ++j) {
            A[(size_t)i * N + j] = av(i, j);
            B[(size_t)i * N + j] = bv(i, j);
        }

    cblas_dgemm(CblasRowMajor, CblasNoTrans, CblasNoTrans,
                N, N, N, 1.0, A, N, B, N, 0.0, C, N);

    double sig = 0.0;
    for (size_t t = 0; t < (size_t)N * N; ++t) sig += C[t];

    mkl_free(A); mkl_free(B); mkl_free(C);
    printf("VALID dgemm sig=%.10g\n", sig);
    return 0;
}
CPP

gcc -O3 -std=c11 /app/dgemm_mkl.c -lmkl_rt -lpthread -lm -ldl -o /app/dgemm_mkl
