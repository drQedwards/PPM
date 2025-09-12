#include "numpy-lib.h"

int vector_add_double(const double* a, const double* b, double* out, size_t n) {
    if (!out) return 1;
    if (n == 0) return 0;
    if (!a || !b) return 2;
    for (size_t i = 0; i < n; ++i) {
        out[i] = a[i] + b[i];
    }
    return 0;
}

double dot_double(const double* a, const double* b, size_t n) {
    if (!a || !b) return 0.0;
    double acc = 0.0;
    for (size_t i = 0; i < n; ++i) {
        acc += a[i] * b[i];
    }
    return acc;
}

void scale_inplace_double(double* a, double alpha, size_t n) {
    if (!a) return;
    for (size_t i = 0; i < n; ++i) {
        a[i] *= alpha;
    }
}
