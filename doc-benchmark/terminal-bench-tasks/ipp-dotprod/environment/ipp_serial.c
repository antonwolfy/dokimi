/* Serial reference: dot product over two deterministic integer-valued vectors. */
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv) {
    long n = 4000000;
    if (argc > 1) {
        char *end = NULL;
        errno = 0;
        n = strtol(argv[1], &end, 10);
        if (errno != 0 || end == argv[1] || *end != '\0') {
            fprintf(stderr, "INVALID_ARGUMENTS\n");
            return 2;
        }
    }
    /* Upper bound keeps the (int)n cast in the IPP variant well-defined. */
    if (n < 1 || n > INT_MAX) {
        fprintf(stderr, "INVALID_ARGUMENTS\n");
        return 2;
    }
    double dot = 0.0;
    for (long i = 0; i < n; ++i) {
        double a = (double)(((i * 7 + 1) % 101) - 50);
        double b = (double)(((i * 13 + 3) % 97) - 48);
        dot += a * b;
    }
    printf("VALID ipp dot=%.10g\n", dot);
    return 0;
}
