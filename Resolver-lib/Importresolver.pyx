# distutils: language = c
# cython: language_level=3

from libc.stddef cimport size_t
from libc.stdlib cimport malloc, free
from libc.string cimport strcpy, strlen
cimport cython

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

@cython.cfunc
cdef char* _dup(bytes b) nogil:
    cdef size_t n = len(b)
    cdef char* p = <char*> malloc(n + 1)
    if p == NULL:
        return NULL
    # Copy bytes and NUL-terminate
    for size_t i in range(n):
        p[i] = <char> b[i]
    p[n] = 0
    return p

@cython.cfunc
cdef const char** _dup_argv(list items) nogil:
    cdef Py_ssize_t i, n = len(items)
    cdef const char **argv = <const char **> malloc(n * sizeof(const char *))
    if argv == NULL:
        return NULL
    for i in range(n):
        # we accept str or bytes; encode to UTF-8 bytes
        with gil:
            v = items[i]
            if isinstance(v, bytes):
                b = <bytes> v
            else:
                b = (<str> v).encode('utf-8')
        argv[i] = _dup(b)
        if argv[i] == NULL:
            # free partial
            for Py_ssize_t j in range(i):
                free(<void*> argv[j])
            free(argv)
            return NULL
    return argv

@cython.boundscheck(False)
@cython.wraparound(False)
def resolve(root: str,
            requirements: list,
            index_url: str = "https://pypi.org/simple",
            extra_index_url: str | None = None,
            python_exec: str | None = None,
            helper_path: str = "Resolver-lib/importresolver.py") -> int:
    """
    Call the C shim which launches the Python helper to resolve dependencies and
    emit:
      - <root>/.ppm/lock.json
      - <root>/pylock.toml
      - <root>/resolver.py
      - <root>/.ppm/matrix_inputs.txt
      - <root>/.ppm/matrix_plan.json
    Returns the C function's return code (0 on success).
    """
    if python_exec is None:
        python_exec = "python3"

    cdef bytes broot = root.encode("utf-8")
    cdef bytes bindex = index_url.encode("utf-8")
    cdef bytes bextra = extra_index_url.encode("utf-8") if extra_index_url is not None else b""
    cdef bytes bpy = python_exec.encode("utf-8")
    cdef bytes bhelper = helper_path.encode("utf-8")

    cdef char *c_root = _dup(broot)
    cdef char *c_index = _dup(bindex)
    cdef char *c_extra = _dup(bextra) if extra_index_url is not None else NULL
    cdef char *c_py = _dup(bpy)
    cdef char *c_helper = _dup(bhelper)

    if c_root == NULL or c_index == NULL or c_py == NULL or c_helper == NULL or (extra_index_url is not None and c_extra == NULL):
        if c_root: free(c_root)
        if c_index: free(c_index)
        if c_extra: free(c_extra)
        if c_py: free(c_py)
        if c_helper: free(c_helper)
        raise MemoryError()

    cdef const char **c_reqs = NULL
    with nogil:
        c_reqs = _dup_argv(requirements)
    if c_reqs == NULL:
        free(c_root); free(c_index); 
        if c_extra: free(c_extra)
        free(c_py); free(c_helper)
        raise MemoryError()

    cdef int rc
    with nogil:
        rc = ir_resolve_with_helper(c_root, c_reqs, <size_t> len(requirements),
                                    c_index,
                                    c_extra if extra_index_url is not None else NULL,
                                    c_py,
                                    c_helper)

    # cleanup
    for i in range(len(requirements)):
        free(<void*> c_reqs[i])
    free(c_reqs)
    free(c_root); free(c_index); 
    if c_extra: free(c_extra)
    free(c_py); free(c_helper)

    return rc

def matrix_verify(root: str,
                  inputs_path: str | None = None,
                  report_path: str | None = None) -> tuple[int, int]:
    """
    GPU-verify artifact hashes with CUDA.
    Returns (rc, mismatch_count).
    Writes JSON report at:
      <root>/.ppm/matrix_report.json
    """
    if inputs_path is None:
        inputs_path = os.path.join(root, ".ppm", "matrix_inputs.txt")
    if report_path is None:
        report_path = os.path.join(root, ".ppm", "matrix_report.json")

    cdef bytes broot = root.encode("utf-8")
    cdef bytes binputs = inputs_path.encode("utf-8")
    cdef bytes breport = report_path.encode("utf-8")

    cdef char *c_root = _dup(broot)
    cdef char *c_inputs = _dup(binputs)
    cdef char *c_report = _dup(breport)
    if c_root == NULL or c_inputs == NULL or c_report == NULL:
        if c_root: free(c_root)
        if c_inputs: free(c_inputs)
        if c_report: free(c_report)
        raise MemoryError()

    cdef int mismatches = -1
    cdef int rc
    with nogil:
        rc = ir_matrix_verify_cuda(c_root, c_inputs, c_report, &mismatches)

    free(c_root); free(c_inputs); free(c_report)
    return rc, mismatches

# small Python helpers
import os

def resolve_and_verify(root: str,
                       requirements: list,
                       index_url: str = "https://pypi.org/simple",
                       extra_index_url: str | None = None,
                       helper_path: str = "Resolver-lib/importresolver.py",
                       python_exec: str | None = None) -> dict:
    """
    Convenience wrapper:
      1) resolve(...)
      2) matrix_verify(...)
      3) run CPU verifier <root>/resolver.py

    Returns a dict with fields:
      {"resolve_rc": int, "matrix_rc": int, "mismatches": int, "cpu_verify_rc": int}
    """
    rc = resolve(root, requirements, index_url=index_url,
                 extra_index_url=extra_index_url,
                 python_exec=python_exec,
                 helper_path=helper_path)
    mrc, mism = matrix_verify(root)
    cpu_rc = 127
    verifier = os.path.join(root, "resolver.py")
    if os.path.exists(verifier):
        cpu_rc = os.system(f"{python_exec or 'python3'} {verifier}")
        if cpu_rc != 0 and os.name != "nt":
            cpu_rc = (cpu_rc >> 8) & 0xff
    return {
        "resolve_rc": rc,
        "matrix_rc": mrc,
        "mismatches": mism,
        "cpu_verify_rc": cpu_rc,
    }
