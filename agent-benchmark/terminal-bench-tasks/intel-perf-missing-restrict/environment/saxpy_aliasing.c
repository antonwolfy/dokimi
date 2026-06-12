#include <math.h>
#include <stdio.h>
#include <stdlib.h>

static void saxpy_many(const double *x, const double *y, double *out, size_t n, int iterations) {
    for (int iter = 0; iter < iterations; ++iter) {
        const double a = 1.000001 + (double)(iter & 7) * 0.000001;
        for (size_t i = 0; i < n; ++i) {
            out[i] = a * x[i] + y[i];
        }
    }
}

int main(int argc, char **argv) {
    const size_t n = argc > 1 ? strtoull(argv[1], NULL, 10) : 2000000ULL;
    const int iterations = argc > 2 ? atoi(argv[2]) : 40;
    if (n == 0 || iterations < 1) return 2;
    double *x = malloc(n * sizeof(double));
    double *y = malloc(n * sizeof(double));
    double *out = malloc(n * sizeof(double));
    if (!x || !y || !out) return 3;
    for (size_t i = 0; i < n; ++i) {
        x[i] = (double)((i * 17u + 3u) % 257u) * 0.25;
        y[i] = (double)((i * 31u + 5u) % 509u) * 0.125;
        out[i] = 0.0;
    }
    saxpy_many(x, y, out, n, iterations);
    double checksum = 0.0;
    for (size_t i = 0; i < n; i += 97) checksum += out[i];
    if (!isfinite(checksum)) return 1;
    printf("VALID checksum=%.17g\n", checksum);
    free(x); free(y); free(out);
    return 0;
}
