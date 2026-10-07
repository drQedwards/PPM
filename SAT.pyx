# SAT.pyx - CDCL SAT solver in Cython (C mode; needs no C++ compiler and no NumPy)
# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False
# cython: cdivision=True

"""
CDCL SAT solver compiled with Cython.

The algorithm matches SAT.py: two watched literals, first-UIP clause learning
(every learned clause is implied by the formula), activity-based branching,
phase saving, and restarts whose interval grows by 1.5x. With
``use_clause_learning = False`` it runs plain DPLL with chronological
backtracking. Variable selection is a linear scan, and learned clauses are
never deleted, so it is meant for small and medium instances. The worst case
is exponential. Measured timings: docs/SAT_SOLVERS.md.

Build (the extension module is named ``SAT``, so build it outside the repo root,
otherwise it shadows SAT.py):

    mkdir -p build/sat_pyx && cp SAT.pyx build/sat_pyx/
    cd build/sat_pyx && cythonize -i -3 SAT.pyx

tests/test_sat_pyx.py builds it in a temporary directory and checks it against
exhaustive search for n <= 10 (skipped when Cython or a C compiler is missing).
"""

from libc.stdlib cimport free, calloc, realloc
from libc.time cimport clock, CLOCKS_PER_SEC

# Result codes returned as the first element of CythonSATSolver.solve().
SAT = 0
UNSAT = 1
UNKNOWN = 2
TIMEOUT = 3


cdef struct IntVec:
    int* data
    int size
    int cap


cdef int vec_push(IntVec* v, int x) except -1:
    cdef int ncap
    cdef int* nd
    if v.size == v.cap:
        ncap = v.cap * 2 if v.cap > 0 else 4
        nd = <int*>realloc(v.data, ncap * sizeof(int))
        if nd == NULL:
            raise MemoryError()
        v.data = nd
        v.cap = ncap
    v.data[v.size] = x
    v.size += 1
    return 0


cdef inline int lit_code(int lit) noexcept:
    # Literal x -> 2x, literal -x -> 2x + 1. Negation flips the low bit.
    return 2 * lit if lit > 0 else -2 * lit + 1


cdef inline int code_lit(int code) noexcept:
    return (code >> 1) if (code & 1) == 0 else -(code >> 1)


cdef class CythonSATSolver:
    """CDCL / DPLL SAT solver over variables 1..num_vars."""

    cdef int num_vars
    cdef IntVec* clauses          # literal codes; positions 0 and 1 are the watches
    cdef int nclauses
    cdef int clause_cap
    cdef IntVec kind              # per clause: 0 original, 1 learned
    cdef IntVec learned_idx       # learned clause indices, in derivation order
    cdef IntVec* watches          # per literal code: clauses watching it
    cdef signed char* value       # per variable: -1 unassigned, 0 false, 1 true
    cdef int* level
    cdef int* reason              # clause index, -1 for decisions
    cdef int* trail               # literal codes in assignment order
    cdef int trail_size
    cdef int qhead
    cdef int* trail_lim           # trail_lim[i]: trail size when level i+1 began
    cdef char* flipped            # DPLL mode: decision at level i already flipped
    cdef int decision_level
    cdef double* activity
    cdef char* phase
    cdef char* seen
    cdef IntVec tmp
    cdef bint has_empty
    cdef double var_inc
    cdef long long n_decisions
    cdef long long n_propagations
    cdef long long n_conflicts
    cdef long long n_restarts
    cdef double start_time

    cdef public bint use_vsids
    cdef public bint use_phase_saving
    cdef public bint use_clause_learning
    cdef public double var_decay
    cdef public double clause_decay   # accepted for compatibility; clauses are never deleted
    cdef public int restart_interval
    cdef public int max_conflicts

    def __cinit__(self, int num_vars, int num_clauses=100):
        if num_vars < 0:
            raise ValueError("num_vars must be >= 0")
        self.num_vars = num_vars
        self.clause_cap = num_clauses if num_clauses > 4 else 4
        self.clauses = <IntVec*>calloc(self.clause_cap, sizeof(IntVec))
        self.watches = <IntVec*>calloc(2 * (num_vars + 1), sizeof(IntVec))
        self.value = <signed char*>calloc(num_vars + 1, sizeof(signed char))
        self.level = <int*>calloc(num_vars + 1, sizeof(int))
        self.reason = <int*>calloc(num_vars + 1, sizeof(int))
        self.trail = <int*>calloc(num_vars + 1, sizeof(int))
        self.trail_lim = <int*>calloc(num_vars + 1, sizeof(int))
        self.flipped = <char*>calloc(num_vars + 2, sizeof(char))
        self.activity = <double*>calloc(num_vars + 1, sizeof(double))
        self.phase = <char*>calloc(num_vars + 1, sizeof(char))
        self.seen = <char*>calloc(num_vars + 1, sizeof(char))
        if (self.clauses == NULL or self.watches == NULL or self.value == NULL or
                self.level == NULL or self.reason == NULL or self.trail == NULL or
                self.trail_lim == NULL or self.flipped == NULL or self.activity == NULL or
                self.phase == NULL or self.seen == NULL):
            raise MemoryError()
        self.var_inc = 1.0
        self.use_vsids = True
        self.use_phase_saving = True
        self.use_clause_learning = True
        self.var_decay = 0.95
        self.clause_decay = 0.999
        self.restart_interval = 100
        self.max_conflicts = 100000
        self._reset_assignment()

    def __dealloc__(self):
        cdef int i
        if self.clauses != NULL:
            for i in range(self.nclauses):
                free(self.clauses[i].data)
            free(self.clauses)
        if self.watches != NULL:
            for i in range(2 * (self.num_vars + 1)):
                free(self.watches[i].data)
            free(self.watches)
        free(self.kind.data)
        free(self.learned_idx.data)
        free(self.tmp.data)
        free(self.value)
        free(self.level)
        free(self.reason)
        free(self.trail)
        free(self.trail_lim)
        free(self.flipped)
        free(self.activity)
        free(self.phase)
        free(self.seen)

    # ------------------------------------------------------------ helpers

    cdef void _reset_assignment(self) noexcept:
        cdef int v
        for v in range(self.num_vars + 1):
            self.value[v] = -1
            self.reason[v] = -1
            self.level[v] = 0
        self.trail_size = 0
        self.qhead = 0
        self.decision_level = 0

    cdef inline int _lit_value(self, int code) noexcept:
        # 1 true, 0 false, -1 unassigned
        cdef signed char v = self.value[code >> 1]
        if v < 0:
            return -1
        return v ^ (code & 1)

    cdef int _store_tmp_clause(self, int learned) except -1:
        """Append self.tmp as a new clause; watch positions 0 and 1. Returns its index."""
        cdef IntVec* nc
        cdef int i, ncap, idx
        if self.nclauses == self.clause_cap:
            ncap = self.clause_cap * 2
            nc = <IntVec*>realloc(self.clauses, ncap * sizeof(IntVec))
            if nc == NULL:
                raise MemoryError()
            for i in range(self.clause_cap, ncap):
                nc[i].data = NULL
                nc[i].size = 0
                nc[i].cap = 0
            self.clauses = nc
            self.clause_cap = ncap
        idx = self.nclauses
        self.nclauses += 1
        for i in range(self.tmp.size):
            vec_push(&self.clauses[idx], self.tmp.data[i])
        vec_push(&self.kind, learned)
        if learned:
            vec_push(&self.learned_idx, idx)
        if self.tmp.size >= 2:
            vec_push(&self.watches[self.tmp.data[0]], idx)
            vec_push(&self.watches[self.tmp.data[1]], idx)
        return idx

    cdef void _assign(self, int code, int why) noexcept:
        cdef int v = code >> 1
        self.value[v] = 1 - (code & 1)
        self.level[v] = self.decision_level
        self.reason[v] = why
        self.trail[self.trail_size] = code
        self.trail_size += 1
        if self.use_phase_saving:
            self.phase[v] = 1 - (code & 1)
        self.n_propagations += 1

    cdef int _propagate(self) except -2:
        """Two-watched-literal propagation. Returns a falsified clause index or -1."""
        cdef int p, false_code, i, j, k, ci, t
        cdef IntVec* ws
        cdef IntVec* c
        cdef bint found
        while self.qhead < self.trail_size:
            p = self.trail[self.qhead]
            self.qhead += 1
            false_code = p ^ 1
            ws = &self.watches[false_code]
            i = 0
            j = 0
            while i < ws.size:
                ci = ws.data[i]
                i += 1
                c = &self.clauses[ci]
                if c.data[0] == false_code:
                    c.data[0] = c.data[1]
                    c.data[1] = false_code
                if self._lit_value(c.data[0]) == 1:
                    ws.data[j] = ci
                    j += 1
                    continue
                found = False
                for k in range(2, c.size):
                    if self._lit_value(c.data[k]) != 0:
                        t = c.data[1]
                        c.data[1] = c.data[k]
                        c.data[k] = t
                        vec_push(&self.watches[c.data[1]], ci)
                        found = True
                        break
                if found:
                    continue
                ws.data[j] = ci
                j += 1
                if self._lit_value(c.data[0]) == 0:
                    while i < ws.size:
                        ws.data[j] = ws.data[i]
                        j += 1
                        i += 1
                    ws.size = j
                    self.qhead = self.trail_size
                    return ci
                self._assign(c.data[0], ci)
            ws.size = j
        return -1

    cdef void _bump(self, int v) noexcept:
        cdef int u
        self.activity[v] += self.var_inc
        if self.activity[v] > 1e100:
            for u in range(1, self.num_vars + 1):
                self.activity[u] *= 1e-100
            self.var_inc *= 1e-100

    cdef int _analyze(self, int confl) except -2:
        """First-UIP analysis into self.tmp (asserting literal first, highest-level
        literal second). Returns the backtrack level."""
        cdef int counter = 0
        cdef int index = self.trail_size - 1
        cdef int ci = confl
        cdef int pvar = 0
        cdef int p = 0
        cdef int k, q, v, best, bt
        cdef IntVec* c
        self.tmp.size = 0
        vec_push(&self.tmp, 0)
        while True:
            c = &self.clauses[ci]
            for k in range(c.size):
                q = c.data[k]
                v = q >> 1
                if v == pvar or self.seen[v] or self.level[v] == 0:
                    continue
                self.seen[v] = 1
                if self.use_vsids:
                    self._bump(v)
                if self.level[v] >= self.decision_level:
                    counter += 1
                else:
                    vec_push(&self.tmp, q)
            while not self.seen[self.trail[index] >> 1]:
                index -= 1
            p = self.trail[index]
            index -= 1
            pvar = p >> 1
            self.seen[pvar] = 0
            counter -= 1
            if counter == 0:
                break
            ci = self.reason[pvar]
        self.tmp.data[0] = p ^ 1
        for k in range(1, self.tmp.size):
            self.seen[self.tmp.data[k] >> 1] = 0
        bt = 0
        if self.tmp.size > 1:
            best = 1
            for k in range(2, self.tmp.size):
                if self.level[self.tmp.data[k] >> 1] > self.level[self.tmp.data[best] >> 1]:
                    best = k
            q = self.tmp.data[1]
            self.tmp.data[1] = self.tmp.data[best]
            self.tmp.data[best] = q
            bt = self.level[self.tmp.data[1] >> 1]
        return bt

    cdef void _backtrack(self, int lvl) noexcept:
        cdef int i, v, lim
        if self.decision_level > lvl:
            lim = self.trail_lim[lvl]
            i = self.trail_size - 1
            while i >= lim:
                v = self.trail[i] >> 1
                self.value[v] = -1
                self.reason[v] = -1
                i -= 1
            self.trail_size = lim
            self.qhead = lim
            self.decision_level = lvl

    cdef void _new_level(self, int code, char was_flipped) noexcept:
        self.trail_lim[self.decision_level] = self.trail_size
        self.decision_level += 1
        self.flipped[self.decision_level] = was_flipped
        self._assign(code, -1)

    cdef bint _flip_last_decision(self) noexcept:
        """DPLL mode: flip the deepest decision not flipped yet. False if none is left."""
        cdef int lvl = self.decision_level
        cdef int dec
        while lvl > 0 and self.flipped[lvl]:
            lvl -= 1
        if lvl == 0:
            return False
        dec = self.trail[self.trail_lim[lvl - 1]]
        self._backtrack(lvl - 1)
        self._new_level(dec ^ 1, 1)
        return True

    cdef int _choose_variable(self) noexcept:
        """Highest activity (ties: lowest index) with use_vsids, else lowest index. 0 if none."""
        cdef int v
        cdef int best = 0
        cdef double best_act = -1.0
        for v in range(1, self.num_vars + 1):
            if self.value[v] < 0:
                if not self.use_vsids:
                    return v
                if self.activity[v] > best_act:
                    best_act = self.activity[v]
                    best = v
        return best

    # ------------------------------------------------------------ public API

    cpdef add_clause(self, list literals):
        """Add a clause given as signed ints. Duplicate literals are merged and
        tautologies are dropped. ValueError if a literal is 0 or out of range."""
        cdef int lit
        seen = set()
        for l in literals:
            lit = l
            if lit == 0 or abs(lit) > self.num_vars:
                raise ValueError(f"literal {l} out of range for {self.num_vars} variables")
            if -lit in seen:
                return
            seen.add(lit)
        self._reset_assignment()
        self.tmp.size = 0
        added = set()
        for l in literals:
            lit = l
            if lit not in added:
                added.add(lit)
                vec_push(&self.tmp, lit_code(lit))
        if self.tmp.size == 0:
            self.has_empty = True
        self._store_tmp_clause(0)

    cpdef tuple solve(self):
        """Returns (SAT, model), (UNSAT, None) or (TIMEOUT, None) after more than
        max_conflicts conflicts in this call. The model maps every variable to a bool."""
        cdef int ci, confl, bt, v, idx, lv
        cdef long long conflicts = 0
        cdef long long since_restart = 0
        cdef long long restart_limit = self.restart_interval if self.restart_interval > 0 else 1
        cdef IntVec* c
        self.start_time = clock() / <double>CLOCKS_PER_SEC
        self._reset_assignment()
        if self.has_empty:
            return (UNSAT, None)
        for ci in range(self.nclauses):
            c = &self.clauses[ci]
            if c.size == 1:
                lv = self._lit_value(c.data[0])
                if lv == 0:
                    return (UNSAT, None)
                if lv < 0:
                    self._assign(c.data[0], ci)
        while True:
            confl = self._propagate()
            if confl >= 0:
                self.n_conflicts += 1
                conflicts += 1
                since_restart += 1
                if self.decision_level == 0:
                    return (UNSAT, None)
                if conflicts > self.max_conflicts:
                    self._reset_assignment()
                    return (TIMEOUT, None)
                if self.use_clause_learning:
                    bt = self._analyze(confl)
                    self._backtrack(bt)
                    idx = self._store_tmp_clause(1)
                    self._assign(self.tmp.data[0], idx)
                    if self.use_vsids:
                        self.var_inc /= self.var_decay
                elif not self._flip_last_decision():
                    return (UNSAT, None)
                continue
            if self.use_clause_learning and since_restart >= restart_limit:
                self._backtrack(0)
                self.n_restarts += 1
                since_restart = 0
                if restart_limit < (1LL << 60):
                    restart_limit = restart_limit * 3 // 2 + 1
                continue
            v = self._choose_variable()
            if v == 0:
                for ci in range(self.nclauses):
                    if self.kind.data[ci] == 0 and not self._clause_true(ci):
                        raise RuntimeError("internal error: model does not satisfy the formula")
                return (SAT, self._get_model())
            self.n_decisions += 1
            if self.use_phase_saving and self.phase[v]:
                self._new_level(2 * v, 0)
            else:
                self._new_level(2 * v + 1, 0)

    cdef bint _clause_true(self, int ci) noexcept:
        cdef int k
        cdef IntVec* c = &self.clauses[ci]
        for k in range(c.size):
            if self._lit_value(c.data[k]) == 1:
                return True
        return False

    cdef dict _get_model(self):
        model = {}
        cdef int v
        for v in range(1, self.num_vars + 1):
            if self.value[v] >= 0:
                model[v] = self.value[v] == 1
        return model

    cpdef bint validate(self, dict model):
        """True when ``model`` (var -> bool) satisfies every original clause."""
        cdef int ci, k, lit
        cdef IntVec* c
        for ci in range(self.nclauses):
            if self.kind.data[ci] != 0:
                continue
            c = &self.clauses[ci]
            ok = False
            for k in range(c.size):
                lit = code_lit(c.data[k])
                if abs(lit) in model and bool(model[abs(lit)]) == (lit > 0):
                    ok = True
                    break
            if not ok:
                return False
        return True

    def learned_clauses(self):
        """Learned clauses (lists of signed ints) in derivation order."""
        cdef int i, k, ci
        out = []
        for i in range(self.learned_idx.size):
            ci = self.learned_idx.data[i]
            out.append([code_lit(self.clauses[ci].data[k]) for k in range(self.clauses[ci].size)])
        return out

    def get_stats(self):
        """Solver statistics (cumulative over solve() calls; cpu_time is for the last call)."""
        return {
            'decisions': self.n_decisions,
            'propagations': self.n_propagations,
            'conflicts': self.n_conflicts,
            'learned_clauses': self.learned_idx.size,
            'restarts': self.n_restarts,
            'cpu_time': clock() / <double>CLOCKS_PER_SEC - self.start_time
        }

    def generate_ppm(self, str filename, dict model=None):
        """Write a PPM image: one row per original clause, one column per variable.
        Green/red: literal true/false under ``model``; blue: unassigned (light = positive)."""
        cdef int ci, k, lit, var, scale, img_h, img_w, y, x, rows
        rows = 0
        for ci in range(self.nclauses):
            if self.kind.data[ci] == 0:
                rows += 1
        if rows == 0 or self.num_vars == 0:
            return
        scale = min(10, max(1, 1000 // max(rows, self.num_vars)))
        img_h = rows * scale
        img_w = self.num_vars * scale
        img = bytearray(img_h * img_w * 3)
        row = 0
        for ci in range(self.nclauses):
            if self.kind.data[ci] != 0:
                continue
            for k in range(self.clauses[ci].size):
                lit = code_lit(self.clauses[ci].data[k])
                var = abs(lit) - 1
                if model and (var + 1) in model:
                    if bool(model[var + 1]) == (lit > 0):
                        rgb = (0, 255, 0)
                    else:
                        rgb = (255, 0, 0)
                else:
                    rgb = (0, 0, 255 if lit > 0 else 128)
                for y in range(row * scale, (row + 1) * scale):
                    for x in range(var * scale, (var + 1) * scale):
                        img[(y * img_w + x) * 3:(y * img_w + x) * 3 + 3] = bytes(rgb)
            row += 1
        with open(filename, 'wb') as f:
            f.write(f"P6\n{img_w} {img_h}\n255\n".encode())
            f.write(bytes(img))


class PySATSolver:
    """Python-friendly wrapper for CythonSATSolver."""

    def __init__(self, num_vars, config=None):
        self.solver = CythonSATSolver(num_vars)
        if config:
            self.solver.use_vsids = config.get('use_vsids', True)
            self.solver.use_phase_saving = config.get('use_phase_saving', True)
            self.solver.use_clause_learning = config.get('use_clause_learning', True)
            self.solver.var_decay = config.get('var_decay', 0.95)
            self.solver.clause_decay = config.get('clause_decay', 0.999)
            self.solver.restart_interval = config.get('restart_interval', 100)
            self.solver.max_conflicts = config.get('max_conflicts', 100000)

    def add_clause(self, literals):
        """Add a clause to the formula"""
        self.solver.add_clause(list(literals))

    def solve(self):
        """Returns ('SAT', model), ('UNSAT', None) or ('TIMEOUT', None)."""
        result, model = self.solver.solve()
        result_map = {SAT: 'SAT', UNSAT: 'UNSAT', UNKNOWN: 'UNKNOWN', TIMEOUT: 'TIMEOUT'}
        return result_map[result], model

    def validate(self, model):
        """Validate a solution"""
        return self.solver.validate(model)

    def get_stats(self):
        """Get solving statistics"""
        return self.solver.get_stats()

    def visualize(self, filename='sat_visualization.ppm', model=None):
        """Generate PPM visualization"""
        self.solver.generate_ppm(filename, model)

    @classmethod
    def from_dimacs(cls, filename):
        """Create a solver from a DIMACS file (comments skipped; clauses end at 0
        and may span lines). Returns None if there is no ``p cnf`` header."""
        solver = None
        current = []
        with open(filename, 'r') as f:
            for line in f:
                parts = line.split()
                if not parts or parts[0] == 'c' or parts[0].startswith('%'):
                    continue
                if parts[0] == 'p':
                    solver = cls(int(parts[2]))
                    continue
                if solver is None:
                    continue
                for tok in parts:
                    lit = int(tok)
                    if lit == 0:
                        solver.add_clause(current)
                        current = []
                    else:
                        current.append(lit)
        if solver is not None and current:
            solver.add_clause(current)
        return solver
