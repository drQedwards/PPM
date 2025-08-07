# distutils: language = c
# cython: boundscheck=False, wraparound=False

from libc.stdlib cimport free, strdup
from libc.string  cimport strcmp

cdef extern from "CLI.h":
    int ppm_cli_import(const char *pkg_spec, int verbose)

def import_packages(list specs, bint verbose=False):
    """Fast path: batch import."""
    cdef bytes spec_b
    for spec in specs:
        spec_b = spec.encode("utf-8")
        ppm_cli_import(<const char*>spec_b, <int>verbose)
