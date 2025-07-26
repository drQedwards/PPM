# distutils: language = c
# cython: language_level=3

from libc.stddef cimport size_t

cdef extern from "importresolver.h":
    int ir_resolve_with_helper(
        const char *root,
        const char **reqs, size_t n_reqs,
        const char *index_url,
        const char *extra_index_url,
        const char *py_exec,
        const char *helper_path
    )

    int ir_matrix_verify_cuda(
        const char *root,
        const char *matrix_inputs_path,
        const char *report_path,
        int *out_mismatch_count
    )
