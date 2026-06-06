#!/usr/bin/env bash
set -euo pipefail

cat > /app/ipp_dot.c <<'CPP'
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <ipp.h>

int main(int argc, char **argv) {
    long n = argc > 1 ? atol(argv[1]) : 4000000;
    /* IPP lengths are int; reject anything that would truncate on the cast. */
    if (n < 1 || n > INT_MAX) {
        fprintf(stderr, "INVALID_ARGUMENTS\n");
        return 2;
    }
    Ipp64f *a = ippsMalloc_64f((int)n);
    Ipp64f *b = ippsMalloc_64f((int)n);
    if (!a || !b) return 3;
    for (long i = 0; i < n; ++i) {
        a[i] = (double)(((i * 7 + 1) % 101) - 50);
        b[i] = (double)(((i * 13 + 3) % 97) - 48);
    }
    Ipp64f dot = 0.0;
    IppStatus st = ippsDotProd_64f(a, b, (int)n, &dot);
    ippsFree(a);
    ippsFree(b);
    if (st != ippStsNoErr) {
        fprintf(stderr, "IPP_ERROR %d\n", st);
        return 4;
    }
    printf("VALID ipp dot=%.10g\n", dot);
    return 0;
}
CPP

gcc -O3 -std=c11 /app/ipp_dot.c -lipps -lippcore -lm -o /app/ipp_dot
