# distutils: language = c
# cython: language_level=3

# Cython wrapper around the lightweight C kernels in numpy-lib.c/.h

import numpy as np
cimport numpy as cnp

# Required to use the NumPy C-API
cnp.import_array()

cdef extern from "numpy-lib.h":
    int vector_add_double(const double* a, const double* b, double* out, size_t n)
    double dot_double(const double* a, const double* b, size_t n)
    void scale_inplace_double(double* a, double alpha, size_t n)

def vector_add(np.ndarray[cnp.double_t, ndim=1, mode="c"] a,
               np.ndarray[cnp.double_t, ndim=1, mode="c"] b):
    """
    Add two 1D float64 arrays elementwise. Returns a new array.
    """
    if a.ndim != 1 or b.ndim != 1:
        raise ValueError("vector_add: inputs must be 1D")
    if a.shape[0] != b.shape[0]:
        raise ValueError("vector_add: length mismatch")
    cdef Py_ssize_t n = a.shape[0]
    cdef np.ndarray[cnp.double_t, ndim=1, mode="c"] out = np.empty(n, dtype=np.float64)
    cdef int rc = vector_add_double(<const double*> a.data,
                                    <const double*> b.data,
                                    <double*> out.data,
                                    <size_t> n)
    if rc != 0:
        raise RuntimeError("vector_add_double failed with code %d" % rc)
    return out

def dot(np.ndarray[cnp.double_t, ndim=1, mode="c"] a,
        np.ndarray[cnp.double_t, ndim=1, mode="c"] b) -> float:
    """
    Dot product of two 1D float64 arrays. Returns a Python float.
    """
    if a.ndim != 1 or b.ndim != 1:
        raise ValueError("dot: inputs must be 1D")
    if a.shape[0] != b.shape[0]:
        raise ValueError("dot: length mismatch")
    cdef Py_ssize_t n = a.shape[0]
    cdef double res = dot_double(<const double*> a.data,
                                 <const double*> b.data,
                                 <size_t> n)
    return float(res)

def scale_inplace(np.ndarray[cnp.double_t, ndim=1, mode="c"] a, double alpha):
    """
    In-place scale: a *= alpha
    """
    if a.ndim != 1:
        raise ValueError("scale_inplace: input must be 1D")
    cdef Py_ssize_t n = a.shape[0]
    scale_inplace_double(<double*> a.data, alpha, <size_t> n)
    return None
