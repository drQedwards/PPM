#ifndef NUMPY_LIB_H
#define NUMPY_LIB_H

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

// Returns 0 on success, nonzero on error (e.g., n == 0 and pointers are NULL).
int vector_add_double(const double* a, const double* b, double* out, size_t n);

// Standard dot product (sum_i a[i]*b[i]).
double dot_double(const double* a, const double* b, size_t n);

// In-place scaling: a[i] *= alpha.
void scale_inplace_double(double* a, double alpha, size_t n);

#ifdef __cplusplus
}
#endif

#endif // NUMPY_LIB_H
