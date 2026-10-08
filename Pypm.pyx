# cython: language_level=3
# distutils: language = c
# distutils: sources = PMLL.c
# distutils: define_macros = PMLL_NO_MAIN=1
"""Cython binding for the PMLL core in PMLL.c / PMLL.h.

* ``Silo``: memory_silo_t, with silo_set, exact peek (key or index), peek_semantic,
  the integer tree written by update_silo, and slot introspection.
* ``embed_text`` / ``cosine_similarity``: the silo's feature-hashing embedding.
* ``solve_sat``: runs PMLL's ``pml_logic_loop`` refine loop on a CNF formula and
  returns the assignment it reaches. The loop is a bounded heuristic, not a
  complete solver. It can stop with variables unassigned (-1) or with a
  non-satisfying assignment, so check the result with ``check_assignment``.
  Use SAT.pyx / SAT.py when an exact SAT/UNSAT answer is needed.

Build (from the repo root)::

    cythonize -i -3 Pypm.pyx      # compiles PMLL.c in via the distutils directive
"""
from libc.stdlib cimport malloc, free


cdef const char *_cs(bytes b):
    if b is None:
        return NULL
    return <const char *> b

cdef extern from "PMLL.h":
    ctypedef struct clause_t:
        int length
        int *literals
    ctypedef struct silo_slot_t:
        char *key
        char *content
        float *embedding
        int resolved
    ctypedef struct memory_silo_t:
        int *tree
        int size
        silo_slot_t *slots
        int embed_dim
        int slot_count
    ctypedef struct pml_t:
        int num_vars
        int num_clauses
        clause_t *clauses
        int *assignment
        memory_silo_t *silo
        int flag
    int PMLL_EMBED_DIM
    memory_silo_t *init_silo(int size)
    void update_silo(memory_silo_t *silo, int var, int value, int depth)
    void free_silo(memory_silo_t *silo)
    int silo_set(memory_silo_t *silo, int index, const char *key, const char *content)
    int peek(memory_silo_t *silo, const char *key, int index, const char **out_value, int *out_index)
    int peek_semantic(memory_silo_t *silo, const char *query, float min_sim,
                      const char **out_value, int *out_index, float *out_sim)
    void silo_embed_text(const char *text, float *out, int dim)
    float silo_cosine_similarity(const float *a, const float *b, int dim)
    pml_t *init_pml(int num_vars, int num_clauses, clause_t *clauses)
    void pml_logic_loop(pml_t *pml_ptr, int max_depth)
    void output_to_ppm(pml_t *pml_ptr, const char *filename)
    void free_pml(pml_t *pml)

EMBED_DIM = PMLL_EMBED_DIM


cdef object _s(const char *p):
    return None if p == NULL else p.decode("utf-8")


cdef class Silo:
    """An owned PMLL memory_silo_t."""
    cdef memory_silo_t *_ptr

    def __cinit__(self, int size=256):
        if size <= 0:
            raise ValueError("size must be positive")
        self._ptr = init_silo(size)
        if self._ptr == NULL:
            raise MemoryError("init_silo failed")

    def __dealloc__(self):
        if self._ptr != NULL:
            free_silo(self._ptr)
            self._ptr = NULL

    @property
    def size(self):
        return self._ptr.size

    @property
    def slot_count(self):
        return self._ptr.slot_count

    def set(self, key, str content, int index=-1):
        """silo_set: store content (and optional key) at index (-1 = next free)."""
        cdef bytes bk = None if key is None else key.encode("utf-8")
        cdef bytes bc = content.encode("utf-8")
        cdef int idx = silo_set(self._ptr, index, _cs(bk), _cs(bc))
        if idx < 0:
            raise ValueError("silo_set failed (silo full or index out of range)")
        return idx

    def peek(self, key=None, int index=-1):
        """Exact lookup by key (or by index when key is None): (content, index) or None."""
        cdef bytes bk = None if key is None else key.encode("utf-8")
        cdef const char *out = NULL
        cdef int idx = -1
        if peek(self._ptr, _cs(bk), index, &out, &idx):
            return (_s(out) or "", idx)
        return None

    def peek_semantic(self, str query, float min_sim=0.5):
        """Best cosine match at or above min_sim: (content, index, similarity) or None."""
        cdef bytes bq = query.encode("utf-8")
        cdef const char *out = NULL
        cdef int idx = -1
        cdef float sim = 0
        if peek_semantic(self._ptr, <const char *> bq, min_sim, &out, &idx, &sim):
            return (_s(out) or "", idx, float(sim))
        return None

    def update(self, int var, int value, int depth=0):
        """update_silo: write tree[var] and propagate (out-of-range var is ignored)."""
        update_silo(self._ptr, var, value, depth)

    def tree(self):
        """Copy of the integer tree (length 2 * size)."""
        return [self._ptr.tree[i] for i in range(2 * self._ptr.size)]

    def slot(self, int index):
        """(key, content, resolved) for a slot index."""
        if index < 0 or index >= self._ptr.size:
            raise IndexError(index)
        cdef silo_slot_t *s = &self._ptr.slots[index]
        return (_s(s.key), _s(s.content), bool(s.resolved))


def embed_text(str text, int dim=PMLL_EMBED_DIM):
    """silo_embed_text: L2-normalised feature-hashing vector of length dim."""
    if dim <= 0:
        raise ValueError("dim must be positive")
    cdef float *buf = <float *> malloc(dim * sizeof(float))
    if buf == NULL:
        raise MemoryError()
    cdef bytes bt = text.encode("utf-8")
    try:
        silo_embed_text(<const char *> bt, buf, dim)
        return [buf[i] for i in range(dim)]
    finally:
        free(buf)


def cosine_similarity(a, b):
    """silo_cosine_similarity over two equal-length float sequences."""
    cdef int n = len(a)
    if n != len(b) or n == 0:
        raise ValueError("vectors must be non-empty and the same length")
    cdef float *x = <float *> malloc(n * sizeof(float))
    cdef float *y = <float *> malloc(n * sizeof(float))
    if x == NULL or y == NULL:
        free(x)
        free(y)
        raise MemoryError()
    try:
        for i in range(n):
            x[i] = a[i]
            y[i] = b[i]
        return float(silo_cosine_similarity(x, y, n))
    finally:
        free(x)
        free(y)


def check_assignment(clauses, assignment):
    """True when every clause has a literal made true by assignment (1/0/-1 per var)."""
    for clause in clauses:
        if not any(0 < abs(l) <= len(assignment) and assignment[abs(l) - 1] == (1 if l > 0 else 0)
                   for l in clause):
            return False
    return True


def solve_sat(int num_vars, list clauses_data, output_file=None, int max_depth=2):
    """Run pml_logic_loop. Returns the assignment list (1 true, 0 false, -1 unassigned).

    Heuristic and bounded: verify with check_assignment(). If output_file is
    given, output_to_ppm writes the assignment as a 1-row PGM image.
    """
    if num_vars <= 0:
        raise ValueError("num_vars must be positive")
    cdef int m = len(clauses_data)
    cdef clause_t *clauses = <clause_t *> malloc((m if m > 0 else 1) * sizeof(clause_t))
    if clauses == NULL:
        raise MemoryError()
    cdef int i, j, k
    for i in range(m):
        clauses[i].length = 0
        clauses[i].literals = NULL
    for i in range(m):
        k = len(clauses_data[i])
        clauses[i].literals = <int *> malloc((k if k > 0 else 1) * sizeof(int))
        if clauses[i].literals == NULL:
            for j in range(i):
                free(clauses[j].literals)
            free(clauses)
            raise MemoryError()
        clauses[i].length = k
        for j in range(k):
            lit = int(clauses_data[i][j])
            if lit == 0 or abs(lit) > num_vars:
                for j in range(i + 1):
                    free(clauses[j].literals)
                free(clauses)
                raise ValueError(f"literal {lit} out of range for {num_vars} variables")
            clauses[i].literals[j] = lit
    cdef pml_t *pml = init_pml(num_vars, m, clauses)
    if pml == NULL:
        for i in range(m):
            free(clauses[i].literals)
        free(clauses)
        raise MemoryError("init_pml failed")
    cdef bytes bout
    try:
        pml_logic_loop(pml, max_depth)
        solution = [pml.assignment[i] for i in range(num_vars)]
        if output_file is not None:
            bout = str(output_file).encode("utf-8")
            output_to_ppm(pml, <const char *> bout)
    finally:
        free_pml(pml)  # frees the clause array and literals as well
    return solution
