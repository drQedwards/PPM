# distutils: language = c
# distutils: sources = PMLL.c

cdef extern from "PMLL.h":
    ctypedef struct clause_t:
        int length
        int *literals
    ctypedef struct memory_silo_t:
        int *tree
        int size
    ctypedef struct pml_t:
        int num_vars
        int num_clauses
        clause_t *clauses
        int *assignment
        memory_silo_t *silo
        int flag
    pml_t *init_pml(int num_vars, int num_clauses, clause_t *clauses)
    void pml_logic_loop(pml_t *pml_ptr, int max_depth)
    void output_to_ppm(pml_t *pml_ptr, const char *filename)
    void free_pml(pml_t *pml)

import cython
import numpy as np
cimport numpy as np

def solve_sat(int num_vars, list clauses_data, str output_file):
    cdef int num_clauses = len(clauses_data)
    cdef clause_t *clauses = <clause_t *>malloc(num_clauses * sizeof(clause_t))
    
    for i in range(num_clauses):
        clauses[i].length = len(clauses_data[i])
        clauses[i].literals = <int *>malloc(clauses[i].length * sizeof(int))
        for j in range(clauses[i].length):
            clauses[i].literals[j] = clauses_data[i][j]

    cdef pml_t *pml = init_pml(num_vars, num_clauses, clauses)
    pml_logic_loop(pml, <int>log2(num_vars))
    
    # Extract solution
    solution = [pml.assignment[i] for i in range(num_vars)]
    output_to_ppm(pml, output_file.encode())
    free_pml(pml)

    for i in range(num_clauses):
        free(clauses[i].literals)
    free(clauses)
    
    return solution

# Setup.py for compilation
from distutils.core import setup
from Cython.Build import cythonize
from distutils.extension import Extension

setup(
    ext_modules=cythonize([
        Extension("pypm", ["pypm.pyx"], libraries=["m"])
    ])
)
