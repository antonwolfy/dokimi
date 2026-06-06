/* Serial naive DFT reference. Computes the magnitude spectrum of a deterministic
 * signal and reports the dominant non-DC bin and the sum of magnitudes.
 */
#include <stdio.h>
#include <stdlib.h>
#include <math.h>

int main(int argc, char **argv) {
    int N = argc > 1 ? atoi(argv[1]) : 2048;
    if (N < 2) {
        fprintf(stderr, "INVALID_ARGUMENTS\n");
        return 2;
    }
    double *x = (double *)malloc(sizeof(double) * N);
    if (!x) return 3;
    const double PI = 3.14159265358979323846;
    for (int i = 0; i < N; ++i)
        x[i] = cos(2.0 * PI * 5.0 * i / N) + 0.5 * sin(2.0 * PI * 12.0 * i / N);

    double summag = 0.0, peakmag = -1.0;
    int peak = 0;
    for (int k = 0; k <= N / 2; ++k) {
        double sr = 0.0, si = 0.0;
        for (int n = 0; n < N; ++n) {
            double ang = -2.0 * PI * k * n / N;
            sr += x[n] * cos(ang);
            si += x[n] * sin(ang);
        }
        double mag = sqrt(sr * sr + si * si);
        summag += mag;
        if (k > 0 && mag > peakmag) { peakmag = mag; peak = k; }
    }

    free(x);
    printf("VALID fft peak=%d sig=%.6f\n", peak, summag);
    return 0;
}
