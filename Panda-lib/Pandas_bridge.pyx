# distutils: language=c
# cython: language_level=3

"""
pandas_bridge.pyx  ────────────────
C-callable wrappers for the high-level helpers defined in
`ppm_panda_lib.pandas`.

Each wrapper has the signature:
    int panda_<cmd>(const char* arg_or_NULL)
and returns 0 on success, non-zero on failure.
"""

from cpython.ref cimport PyObject
from cpython.exc cimport PyErr_Print
from cpython.bytes cimport PyBytes_FromString
from cpython.unicode cimport PyUnicode_FromString

cimport cython

# Utility: import the helper module once and cache it
cdef PyObject* _MOD = NULL

cdef inline PyObject* _get_mod():
    global _MOD
    if _MOD is NULL:
        _MOD = PyImport_ImportModule("ppm_panda_lib.pandas")
        if _MOD is NULL:
            PyErr_Print()
    return _MOD

cdef inline int _call0(char* fname):
    cdef PyObject *mod = _get_mod()
    if mod is NULL:
        return 1
    cdef PyObject *fun = PyObject_GetAttrString(mod, fname)
    if fun is NULL:
        PyErr_Print()
        return 2
    cdef PyObject *rv = PyObject_CallObject(fun, NULL)
    if rv is NULL:
        PyErr_Print()
        return 3
    Py_DECREF(rv)
    return 0

cdef inline int _call1(char* fname, const char* arg):
    cdef PyObject *mod = _get_mod()
    if mod is NULL:
        return 1
    cdef PyObject *fun = PyObject_GetAttrString(mod, fname)
    if fun is NULL:
        PyErr_Print()
        return 2
    cdef PyObject *pyarg = PyUnicode_FromString(arg)
    if pyarg is NULL:
        PyErr_Print()
        return 4
    cdef PyObject *tuple = PyTuple_Pack(1, pyarg)
    Py_DECREF(pyarg)
    cdef PyObject *rv = PyObject_CallObject(fun, tuple)
    Py_DECREF(tuple)
    if rv is NULL:
        PyErr_Print()
        return 3
    Py_DECREF(rv)
    return 0


# ────────────────────────────────────────────────────────
# PUBLIC EXPORTS  (visible to C via dlsym)
# Use “cdef public” so Cython exposes the symbol.
# ────────────────────────────────────────────────────────

cdef public int panda_install(const char* ver):
    """
    If ver == NULL → latest; else 'pandas==ver'
    """
    if ver == NULL or ver[0] == 0:
        return _call0(b"install")
    else:
        return _call1(b"install", ver)


cdef public int panda_cache_wheels():
    return _call0(b"cache")


cdef public int panda_csv_peek(const char* path):
    if path == NULL or path[0] == 0:
        PyErr_SetString(PyExc_ValueError, "csv_peek: path required")
        PyErr_Print()
        return 5
    return _call1(b"csv_peek", path)


cdef public int panda_doctor():
    return _call0(b"doctor")
