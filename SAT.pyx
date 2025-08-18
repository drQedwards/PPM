# SAT.pyx - High-performance Cython implementation
# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False
# cython: cdivision=True

"""
Cython-optimized SAT solver with C-level performance
Compile with: python setup.py build_ext --inplace
"""

from libc.stdlib cimport malloc, free, calloc, realloc
from libc.string cimport memset, memcpy
from libc.math cimport sqrt, log
from libc.time cimport clock, CLOCKS_PER_SEC
from libcpp.vector cimport vector
from libcpp.unordered_map cimport unordered_map
from libcpp.unordered_set cimport unordered_set
from libcpp.queue cimport queue, priority_queue
from libcpp.pair cimport pair
from libcpp cimport bool as cbool

import numpy as np
cimport numpy as cnp
cimport cython

# Initialize NumPy C API
cnp.import_array()

# C-level enums for efficiency
cdef enum SATResult:
    SAT = 0
    UNSAT = 1
    UNKNOWN = 2
    TIMEOUT = 3

cdef enum AssignmentValue:
    UNASSIGNED = -1
    FALSE = 0
    TRUE = 1

# Optimized literal structure
cdef struct CLiteral:
    int var  # Variable (positive or negative)
    
cdef inline CLiteral make_literal(int var) nogil:
    cdef CLiteral lit
    lit.var = var
    return lit

cdef inline int lit_var(CLiteral lit) nogil:
    return abs(lit.var)

cdef inline cbool lit_sign(CLiteral lit) nogil:
    return lit.var > 0

cdef inline CLiteral lit_neg(CLiteral lit) nogil:
    cdef CLiteral neg
    neg.var = -lit.var
    return neg

# Optimized clause structure
cdef struct CClause:
    CLiteral* literals
    int size
    int capacity
    cbool learned
    float activity
    int lbd  # Literal Block Distance for clause deletion

cdef CClause* clause_create(int capacity) nogil:
    cdef CClause* clause = <CClause*>malloc(sizeof(CClause))
    clause.literals = <CLiteral*>malloc(capacity * sizeof(CLiteral))
    clause.size = 0
    clause.capacity = capacity
    clause.learned = False
    clause.activity = 0.0
    clause.lbd = 0
    return clause

cdef void clause_destroy(CClause* clause) nogil:
    if clause != NULL:
        if clause.literals != NULL:
            free(clause.literals)
        free(clause)

cdef void clause_add_literal(CClause* clause, CLiteral lit) nogil:
    if clause.size >= clause.capacity:
        clause.capacity *= 2
        clause.literals = <CLiteral*>realloc(clause.literals, 
                                             clause.capacity * sizeof(CLiteral))
    clause.literals[clause.size] = lit
    clause.size += 1

# Variable state for advanced heuristics
cdef struct CVarState:
    double activity
    int decision_level
    int antecedent  # Clause index
    cbool phase_saving
    int pos_count
    int neg_count

# Watch list node
cdef struct CWatchNode:
    int clause_idx
    CWatchNode* next

# CNF structure
cdef struct CCNF:
    CClause** clauses
    int num_clauses
    int clause_capacity
    int num_vars
    CVarState* var_states
    # Statistics
    int decisions
    int propagations
    int conflicts
    int learned_clauses
    int restarts

cdef CCNF* cnf_create(int num_vars) nogil:
    cdef CCNF* cnf = <CCNF*>calloc(1, sizeof(CCNF))
    cnf.num_vars = num_vars
    cnf.clause_capacity = 100
    cnf.clauses = <CClause**>malloc(cnf.clause_capacity * sizeof(CClause*))
    cnf.var_states = <CVarState*>calloc(num_vars + 1, sizeof(CVarState))
    return cnf

cdef void cnf_destroy(CCNF* cnf) nogil:
    if cnf != NULL:
        for i in range(cnf.num_clauses):
            clause_destroy(cnf.clauses[i])
        free(cnf.clauses)
        free(cnf.var_states)
        free(cnf)

cdef void cnf_add_clause(CCNF* cnf, CClause* clause) nogil:
    if cnf.num_clauses >= cnf.clause_capacity:
        cnf.clause_capacity *= 2
        cnf.clauses = <CClause**>realloc(cnf.clauses, 
                                         cnf.clause_capacity * sizeof(CClause*))
    cnf.clauses[cnf.num_clauses] = clause
    cnf.num_clauses += 1
    
    # Update literal counts
    for i in range(clause.size):
        cdef int var = lit_var(clause.literals[i])
        if lit_sign(clause.literals[i]):
            cnf.var_states[var].pos_count += 1
        else:
            cnf.var_states[var].neg_count += 1

# Optimized solver structure
cdef class CythonSATSolver:
    """High-performance SAT solver implemented in Cython"""
    
    cdef CCNF* cnf
    cdef int* assignment  # -1: unassigned, 0: false, 1: true
    cdef int* trail
    cdef int trail_size
    cdef int* trail_lim
    cdef int num_decisions
    cdef int decision_level
    cdef int* reason  # var -> clause index
    cdef CWatchNode** pos_watches
    cdef CWatchNode** neg_watches
    cdef int* propagate_queue
    cdef int queue_head
    cdef int queue_tail
    cdef int queue_capacity
    
    # Configuration
    cdef cbool use_vsids
    cdef cbool use_phase_saving
    cdef cbool use_clause_learning
    cdef double var_decay
    cdef double clause_decay
    cdef int restart_interval
    cdef int max_conflicts
    
    # Performance monitoring
    cdef double start_time
    
    def __cinit__(self, int num_vars, int num_clauses=100):
        """Initialize solver structures"""
        self.cnf = cnf_create(num_vars)
        self.assignment = <int*>malloc((num_vars + 1) * sizeof(int))
        self.trail = <int*>malloc((num_vars + 1) * sizeof(int))
        self.trail_lim = <int*>malloc((num_vars + 1) * sizeof(int))
        self.reason = <int*>malloc((num_vars + 1) * sizeof(int))
        
        # Initialize watches
        self.pos_watches = <CWatchNode**>calloc(num_vars + 1, sizeof(CWatchNode*))
        self.neg_watches = <CWatchNode**>calloc(num_vars + 1, sizeof(CWatchNode*))
        
        # Initialize propagation queue
        self.queue_capacity = num_vars * 2
        self.propagate_queue = <int*>malloc(self.queue_capacity * sizeof(int))
        
        # Reset state
        self.reset()
        
        # Default configuration
        self.use_vsids = True
        self.use_phase_saving = True
        self.use_clause_learning = True
        self.var_decay = 0.95
        self.clause_decay = 0.999
        self.restart_interval = 100
        self.max_conflicts = 100000
    
    def __dealloc__(self):
        """Clean up allocated memory"""
        cnf_destroy(self.cnf)
        free(self.assignment)
        free(self.trail)
        free(self.trail_lim)
        free(self.reason)
        free(self.propagate_queue)
        
        # Clean up watch lists
        cdef CWatchNode* node
        cdef CWatchNode* next_node
        for i in range(self.cnf.num_vars + 1):
            node = self.pos_watches[i]
            while node != NULL:
                next_node = node.next
                free(node)
                node = next_node
            
            node = self.neg_watches[i]
            while node != NULL:
                next_node = node.next
                free(node)
                node = next_node
        
        free(self.pos_watches)
        free(self.neg_watches)
    
    cdef void reset(self):
        """Reset solver state"""
        for i in range(self.cnf.num_vars + 1):
            self.assignment[i] = UNASSIGNED
            self.reason[i] = -1
        
        self.trail_size = 0
        self.num_decisions = 0
        self.decision_level = 0
        self.queue_head = 0
        self.queue_tail = 0
    
    cpdef add_clause(self, list literals):
        """Add a clause to the CNF formula"""
        cdef CClause* clause = clause_create(len(literals))
        cdef CLiteral lit
        
        for l in literals:
            lit.var = l
            clause_add_literal(clause, lit)
        
        cnf_add_clause(self.cnf, clause)
        self._watch_clause(self.cnf.num_clauses - 1)
    
    cdef void _watch_clause(self, int clause_idx) nogil:
        """Set up watches for a clause"""
        cdef CClause* clause = self.cnf.clauses[clause_idx]
        if clause.size >= 2:
            self._add_watch(clause.literals[0], clause_idx)
            self._add_watch(clause.literals[1], clause_idx)
        elif clause.size == 1:
            self._add_watch(clause.literals[0], clause_idx)
    
    cdef void _add_watch(self, CLiteral lit, int clause_idx) nogil:
        """Add a watch for a literal"""
        cdef CWatchNode* node = <CWatchNode*>malloc(sizeof(CWatchNode))
        node.clause_idx = clause_idx
        
        cdef int var = lit_var(lit)
        if lit_sign(lit):
            node.next = self.pos_watches[var]
            self.pos_watches[var] = node
        else:
            node.next = self.neg_watches[var]
            self.neg_watches[var] = node
    
    cdef cbool _propagate(self) nogil:
        """Unit propagation with two-watched literals"""
        while self.queue_head < self.queue_tail:
            cdef int lit_int = self.propagate_queue[self.queue_head]
            self.queue_head += 1
            
            cdef CLiteral lit
            lit.var = lit_int
            cdef int var = lit_var(lit)
            
            # Process watches for negation of assigned literal
            cdef CWatchNode** watch_list
            if lit_sign(lit):
                watch_list = &self.neg_watches[var]
            else:
                watch_list = &self.pos_watches[var]
            
            cdef CWatchNode* node = watch_list[0]
            cdef CWatchNode* prev = NULL
            
            while node != NULL:
                cdef CClause* clause = self.cnf.clauses[node.clause_idx]
                cdef cbool found_new_watch = False
                cdef int unit_lit = 0
                cdef int unassigned_count = 0
                
                # Look for new watch or check if clause is unit/conflict
                for i in range(clause.size):
                    cdef CLiteral cl = clause.literals[i]
                    cdef int cv = lit_var(cl)
                    
                    if self.assignment[cv] == UNASSIGNED:
                        unassigned_count += 1
                        unit_lit = cl.var
                        if cv != var:  # Can be new watch
                            found_new_watch = True
                            # Move watch to this literal
                            if prev == NULL:
                                watch_list[0] = node.next
                            else:
                                prev.next = node.next
                            
                            cdef CWatchNode* temp = node.next
                            free(node)
                            node = temp
                            
                            self._add_watch(cl, node.clause_idx)
                            break
                    elif (self.assignment[cv] == TRUE and lit_sign(cl)) or \
                         (self.assignment[cv] == FALSE and not lit_sign(cl)):
                        # Clause is satisfied
                        found_new_watch = True
                        break
                
                if not found_new_watch:
                    if unassigned_count == 0:
                        # Conflict
                        return False
                    elif unassigned_count == 1:
                        # Unit clause
                        cdef CLiteral unit
                        unit.var = unit_lit
                        if not self._assign(unit, node.clause_idx):
                            return False
                    
                    prev = node
                    node = node.next
                else:
                    # Already handled in the loop
                    pass
        
        return True
    
    cdef cbool _assign(self, CLiteral lit, int reason) nogil:
        """Assign a variable and add to trail"""
        cdef int var = lit_var(lit)
        cdef int value = TRUE if lit_sign(lit) else FALSE
        
        if self.assignment[var] != UNASSIGNED:
            # Check for conflict
            if self.assignment[var] != value:
                return False
            return True
        
        self.assignment[var] = value
        self.trail[self.trail_size] = lit.var
        self.trail_size += 1
        self.reason[var] = reason
        self.cnf.var_states[var].decision_level = self.decision_level
        
        if self.use_phase_saving:
            self.cnf.var_states[var].phase_saving = value
        
        # Add to propagation queue
        if self.queue_tail >= self.queue_capacity:
            self.queue_capacity *= 2
            self.propagate_queue = <int*>realloc(self.propagate_queue,
                                                 self.queue_capacity * sizeof(int))
        
        self.propagate_queue[self.queue_tail] = lit.var
        self.queue_tail += 1
        self.cnf.propagations += 1
        
        return True
    
    cdef void _backtrack(self, int level) nogil:
        """Backtrack to given decision level"""
        if level < 0:
            level = 0
        
        while self.decision_level > level:
            if self.num_decisions > 0:
                cdef int lim = self.trail_lim[self.num_decisions - 1]
                while self.trail_size > lim:
                    self.trail_size -= 1
                    cdef CLiteral lit
                    lit.var = self.trail[self.trail_size]
                    cdef int var = lit_var(lit)
                    self.assignment[var] = UNASSIGNED
                    self.reason[var] = -1
                    self.cnf.var_states[var].decision_level = -1
                
                self.num_decisions -= 1
            
            self.decision_level -= 1
    
    cdef int _choose_variable(self) nogil:
        """Choose next branching variable using VSIDS"""
        cdef int best_var = 0
        cdef double best_activity = -1.0
        
        for var in range(1, self.cnf.num_vars + 1):
            if self.assignment[var] == UNASSIGNED:
                cdef double activity = self.cnf.var_states[var].activity
                if activity > best_activity:
                    best_activity = activity
                    best_var = var
        
        return best_var
    
    cdef cbool _get_phase(self, int var) nogil:
        """Get phase for variable using phase saving"""
        if self.use_phase_saving:
            return self.cnf.var_states[var].phase_saving
        return False
    
    cdef void _analyze_conflict(self, int conflict_clause, int* learned_clause, 
                                int* learned_size, int* backtrack_level) nogil:
        """Analyze conflict and learn clause (simplified)"""
        # Simplified conflict analysis - in practice, use 1-UIP
        learned_size[0] = 0
        backtrack_level[0] = 0
        
        cdef CClause* clause = self.cnf.clauses[conflict_clause]
        for i in range(clause.size):
            cdef CLiteral lit = clause.literals[i]
            cdef int var = lit_var(lit)
            cdef int level = self.cnf.var_states[var].decision_level
            
            if level < self.decision_level:
                learned_clause[learned_size[0]] = -lit.var
                learned_size[0] += 1
                if level > backtrack_level[0]:
                    backtrack_level[0] = level
    
    cdef void _decay_activities(self) nogil:
        """Decay variable activities for VSIDS"""
        for var in range(1, self.cnf.num_vars + 1):
            self.cnf.var_states[var].activity *= self.var_decay
    
    cpdef tuple solve(self):
        """Main solving method"""
        self.reset()
        self.start_time = clock() / <double>CLOCKS_PER_SEC
        
        # Initial propagation
        if not self._propagate():
            return (UNSAT, None)
        
        cdef int var
        cdef cbool value
        cdef int conflicts = 0
        
        while True:
            # Check timeout
            if conflicts > self.max_conflicts:
                return (TIMEOUT, None)
            
            # Choose variable
            var = self._choose_variable()
            if var == 0:
                # All variables assigned - SAT
                return (SAT, self._get_model())
            
            # Make decision
            self.decision_level += 1
            self.trail_lim[self.num_decisions] = self.trail_size
            self.num_decisions += 1
            
            value = self._get_phase(var)
            cdef CLiteral decision_lit
            decision_lit.var = var if value else -var
            
            if not self._assign(decision_lit, -1):
                # Immediate conflict
                conflicts += 1
                self._backtrack(self.decision_level - 1)
                continue
            
            self.cnf.decisions += 1
            
            # Propagate
            while not self._propagate():
                conflicts += 1
                self.cnf.conflicts += 1
                
                if self.decision_level == 0:
                    return (UNSAT, None)
                
                # Learn clause if enabled
                cdef int backtrack_level = self.decision_level - 1
                
                if self.use_clause_learning:
                    # Simplified learning
                    cdef int learned[1000]  # Static buffer
                    cdef int learned_size = 0
                    
                    # TODO: Implement proper conflict analysis
                    self._backtrack(backtrack_level)
                else:
                    self._backtrack(backtrack_level)
                
                # Restart if needed
                if conflicts % self.restart_interval == 0:
                    self._backtrack(0)
                    self.cnf.restarts += 1
                
                # Decay activities
                if self.use_vsids:
                    self._decay_activities()
                
                break
    
    cdef dict _get_model(self):
        """Extract satisfying assignment"""
        model = {}
        for var in range(1, self.cnf.num_vars + 1):
            if self.assignment[var] != UNASSIGNED:
                model[var] = self.assignment[var] == TRUE
        return model
    
    cpdef cbool validate(self, dict model):
        """Validate a solution"""
        for i in range(self.cnf.num_clauses):
            cdef CClause* clause = self.cnf.clauses[i]
            cdef cbool satisfied = False
            
            for j in range(clause.size):
                cdef CLiteral lit = clause.literals[j]
                cdef int var = lit_var(lit)
                
                if var in model:
                    if (model[var] and lit_sign(lit)) or (not model[var] and not lit_sign(lit)):
                        satisfied = True
                        break
            
            if not satisfied:
                return False
        
        return True
    
    def get_stats(self):
        """Get solver statistics"""
        return {
            'decisions': self.cnf.decisions,
            'propagations': self.cnf.propagations,
            'conflicts': self.cnf.conflicts,
            'learned_clauses': self.cnf.learned_clauses,
            'restarts': self.cnf.restarts,
            'cpu_time': clock() / <double>CLOCKS_PER_SEC - self.start_time
        }
    
    def generate_ppm(self, str filename, dict model=None):
        """Generate PPM visualization of CNF and solution"""
        cdef int height = self.cnf.num_clauses
        cdef int width = self.cnf.num_vars
        
        if height == 0 or width == 0:
            return
        
        # Scale for visibility
        cdef int scale = min(10, max(1, 1000 // max(height, width)))
        cdef int img_height = height * scale
        cdef int img_width = width * scale
        
        # Create image array
        cdef cnp.ndarray[cnp.uint8_t, ndim=3] img = np.zeros((img_height, img_width, 3), dtype=np.uint8)
        
        for i in range(self.cnf.num_clauses):
            cdef CClause* clause = self.cnf.clauses[i]
            
            for j in range(clause.size):
                cdef CLiteral lit = clause.literals[j]
                cdef int var = lit_var(lit) - 1
                
                if var < width:
                    # Determine color based on satisfaction
                    cdef int r = 0, g = 0, b = 0
                    
                    if model and var + 1 in model:
                        cdef cbool lit_sat = (model[var + 1] and lit_sign(lit)) or \
                                            (not model[var + 1] and not lit_sign(lit))
                        if lit_sat:
                            g = 255  # Green for satisfied
                        else:
                            r = 255  # Red for unsatisfied
                    else:
                        b = 255 if lit_sign(lit) else 128  # Blue for unassigned
                    
                    # Fill rectangle
                    for y in range(i * scale, min((i + 1) * scale, img_height)):
                        for x in range(var * scale, min((var + 1) * scale, img_width)):
                            img[y, x, 0] = r
                            img[y, x, 1] = g
                            img[y, x, 2] = b
        
        # Write PPM file
        with open(filename, 'wb') as f:
            f.write(f"P6\n{img_width} {img_height}\n255\n".encode())
            f.write(img.tobytes())


# Python wrapper class for easy use
class PySATSolver:
    """Python-friendly wrapper for Cython SAT solver"""
    
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
        self.solver.add_clause(literals)
    
    def solve(self):
        """Solve the SAT problem"""
        result, model = self.solver.solve()
        
        result_map = {
            SAT: 'SAT',
            UNSAT: 'UNSAT',
            UNKNOWN: 'UNKNOWN',
            TIMEOUT: 'TIMEOUT'
        }
        
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
        """Create solver from DIMACS file"""
        with open(filename, 'r') as f:
            lines = f.readlines()
        
        num_vars = 0
        solver = None
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('c'):
                continue
            
            if line.startswith('p'):
                parts = line.split()
                num_vars = int(parts[2])
                solver = cls(num_vars)
            elif solver:
                literals = [int(x) for x in line.split() if x != '0']
                if literals:
                    solver.add_clause(literals)
        
        return solver
