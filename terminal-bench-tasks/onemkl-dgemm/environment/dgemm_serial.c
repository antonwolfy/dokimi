/* Serial reference for dense double-precision matrix multiply (GEMM).
 * Deterministic integer-valued matrices so the validation signature is exact.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

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
    double *A = (double *)malloc(sizeof(double) * (size_t)N * N);
    double *B = (double *)malloc(sizeof(double) * (size_t)N * N);
    double *C = (double *)calloc((size_t)N * N, sizeof(double));
    if (!A || !B || !C) return 3;

    for (int i = 0; i < N; ++i)
        for (int j = 0; j < N; ++j) {
            A[(size_t)i * N + j] = av(i, j);
            B[(size_t)i * N + j] = bv(i, j);
        }

    for (int i = 0; i < N; ++i)
        for (int k = 0; k < N; ++k) {
            double aik = A[(size_t)i * N + k];
            for (int j = 0; j < N; ++j)
                C[(size_t)i * N + j] += aik * B[(size_t)k * N + j];
        }

    double sig = 0.0;
    for (size_t t = 0; t < (size_t)N * N; ++t) sig += C[t];

    free(A); free(B); free(C);
    printf("VALID dgemm sig=%.10g\n", sig);
    return 0;
}
