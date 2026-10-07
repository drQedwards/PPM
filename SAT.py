#!/usr/bin/env python3
"""
CDCL SAT solver in pure Python, with PPM visualization helpers.

What it does:
- Two watched literals for unit propagation.
- First-UIP conflict analysis. Every learned clause is derived by resolution
  from the formula and earlier learned clauses, so it is implied by the formula.
- Activity-based (VSIDS-style) branching, phase saving, and restarts whose
  interval grows by 1.5x after each restart.
- ``use_clause_learning=False`` switches to plain DPLL with chronological
  backtracking.
- Returns (SATISFIABLE, model) with a value for every variable, checked against
  the input before it is returned; (UNSATISFIABLE, None); or (TIMEOUT, None)
  after ``max_conflicts`` conflicts (default 10000).

What it does not do: clause deletion, preprocessing, or proof output. It is
pure Python and slow next to compiled solvers; see docs/SAT_SOLVERS.md for
measured timings. SAT is NP-complete and the worst case is exponential.
tests/test_sat_py.py checks it against exhaustive search for n <= 10.
"""

import time
import heapq
import random
import logging
from dataclasses import dataclass, field
from typing import List, Set, Dict, Tuple, Optional, Any
from collections import defaultdict, deque
from enum import Enum
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SATResult(Enum):
    """SAT solver result codes"""
    SATISFIABLE = "SAT"
    UNSATISFIABLE = "UNSAT"
    UNKNOWN = "UNKNOWN"
    TIMEOUT = "TIMEOUT"


@dataclass
class Literal:
    """Represents a literal (variable or its negation)"""
    var: int  # Variable index (positive for true, negative for negated)
    
    def __hash__(self):
        return hash(self.var)
    
    def __eq__(self, other):
        return self.var == other.var
    
    def __neg__(self):
        return Literal(-self.var)
    
    def __repr__(self):
        return f"x{abs(self.var)}" if self.var > 0 else f"¬x{abs(self.var)}"
    
    @property
    def is_positive(self) -> bool:
        return self.var > 0
    
    @property
    def variable(self) -> int:
        return abs(self.var)


@dataclass
class Clause:
    """Represents a clause (disjunction of literals)"""
    literals: List[Literal] = field(default_factory=list)
    learned: bool = False
    activity: float = 0.0
    
    def __hash__(self):
        return hash(tuple(sorted(lit.var for lit in self.literals)))
    
    def __repr__(self):
        return "(" + " ∨ ".join(str(lit) for lit in self.literals) + ")"
    
    def is_unit(self, assignment: Dict[int, bool]) -> Optional[Literal]:
        """Check if clause is unit under given assignment"""
        unassigned = []
        for lit in self.literals:
            var = lit.variable
            if var not in assignment:
                unassigned.append(lit)
            elif (assignment[var] and lit.is_positive) or (not assignment[var] and not lit.is_positive):
                return None  # Clause is satisfied
        
        if len(unassigned) == 1:
            return unassigned[0]
        return None
    
    def is_satisfied(self, assignment: Dict[int, bool]) -> bool:
        """Check if clause is satisfied under given assignment"""
        for lit in self.literals:
            var = lit.variable
            if var in assignment:
                if (assignment[var] and lit.is_positive) or (not assignment[var] and not lit.is_positive):
                    return True
        return False
    
    def is_falsified(self, assignment: Dict[int, bool]) -> bool:
        """Check if all literals are false under assignment"""
        for lit in self.literals:
            var = lit.variable
            if var not in assignment:
                return False
            if (assignment[var] and lit.is_positive) or (not assignment[var] and not lit.is_positive):
                return False
        return True


@dataclass
class VarState:
    """State information for a variable"""
    activity: float = 0.0
    decision_level: int = -1
    antecedent: Optional[int] = None  # Clause index that implied this assignment
    phase_saving: Optional[bool] = None
    positive_count: int = 0
    negative_count: int = 0


class WatchedLiterals:
    """Two-watched literals data structure for efficient unit propagation"""
    
    def __init__(self, num_vars: int):
        self.watches: Dict[int, Set[int]] = defaultdict(set)  # literal -> set of clause indices
        
    def watch(self, clause_idx: int, lit: Literal):
        """Add a watch for a literal in a clause"""
        self.watches[lit.var].add(clause_idx)
    
    def unwatch(self, clause_idx: int, lit: Literal):
        """Remove a watch for a literal in a clause"""
        self.watches[lit.var].discard(clause_idx)
    
    def get_watched_clauses(self, lit: Literal) -> Set[int]:
        """Get all clauses watching a literal"""
        return self.watches[lit.var].copy()


class CNF:
    """CNF formula representation"""
    
    def __init__(self, num_vars: int):
        self.num_vars = num_vars
        self.clauses: List[Clause] = []
        self.var_states: List[VarState] = [VarState() for _ in range(num_vars + 1)]
        self.stats = {
            'decisions': 0,
            'propagations': 0,
            'conflicts': 0,
            'learned_clauses': 0,
            'restarts': 0
        }
    
    def add_clause(self, literals: List[int]):
        """Add a clause from a list of signed integers (ValueError if a literal is 0 or out of range)"""
        for lit in literals:
            if lit == 0 or abs(lit) > self.num_vars:
                raise ValueError(f"literal {lit} out of range for {self.num_vars} variables")
        clause = Clause([Literal(lit) for lit in literals])
        self.clauses.append(clause)
        
        # Update literal counts for pure literal detection
        for lit in clause.literals:
            var = lit.variable
            if lit.is_positive:
                self.var_states[var].positive_count += 1
            else:
                self.var_states[var].negative_count += 1
    
    def simplify(self):
        """Simplify the formula by removing tautologies and duplicate literals"""
        simplified = []
        for clause in self.clauses:
            # Remove duplicate literals
            unique_lits = list(set(clause.literals))
            
            # Check for tautology
            is_tautology = False
            for i, lit1 in enumerate(unique_lits):
                for lit2 in unique_lits[i+1:]:
                    if lit1.var == -lit2.var:
                        is_tautology = True
                        break
                if is_tautology:
                    break
            
            if not is_tautology:
                clause.literals = unique_lits
                simplified.append(clause)
        
        self.clauses = simplified
    
    @classmethod
    def from_dimacs(cls, filename: str) -> 'CNF':
        """Parse CNF from DIMACS format file.

        Comment lines (``c``) and ``%`` lines are skipped; a clause ends at ``0``
        and may span lines. Returns None if there is no ``p cnf`` header."""
        with open(filename, 'r') as f:
            lines = f.readlines()

        cnf = None
        current: List[int] = []
        for line in lines:
            parts = line.split()
            if not parts or parts[0] == 'c' or parts[0].startswith('%'):
                continue
            if parts[0] == 'p':
                cnf = cls(int(parts[2]))
                continue
            if cnf is None:
                continue
            for tok in parts:
                lit = int(tok)
                if lit == 0:
                    cnf.add_clause(current)
                    current = []
                else:
                    current.append(lit)
        if cnf is not None and current:
            cnf.add_clause(current)
        return cnf
    
    def to_dimacs(self, filename: str):
        """Write CNF to DIMACS format file"""
        with open(filename, 'w') as f:
            f.write(f"p cnf {self.num_vars} {len(self.clauses)}\n")
            for clause in self.clauses:
                literals = [str(lit.var) for lit in clause.literals]
                f.write(" ".join(literals) + " 0\n")


class SATSolver:
    """CDCL SAT solver: two watched literals, 1-UIP clause learning, VSIDS-style
    branching, phase saving and restarts.

    With ``use_clause_learning=False`` it runs plain DPLL with chronological
    backtracking instead (no learned clauses, no restarts). Both modes are
    complete: given enough conflicts they answer SAT with a model or UNSAT.
    The worst case is exponential in the number of variables.

    Learned clauses are kept in the solver, not added to ``cnf.clauses``. Every
    learned clause is derived by resolution from the formula and earlier learned
    clauses (1-UIP), so it is implied by the formula.
    """

    def __init__(self, cnf: CNF, config: Optional[Dict[str, Any]] = None):
        self.cnf = cnf
        self.assignment: Dict[int, bool] = {}
        self.trail: List[Tuple[int, bool]] = []  # (variable, value)
        self.trail_lim: List[int] = []  # trail length at the start of each decision level
        self.decision_level = 0
        self.watches = WatchedLiterals(cnf.num_vars)  # literal -> indices of clauses watching it
        self.reason: Dict[int, Optional[int]] = {}  # variable -> clause index (None for decisions)

        self.config = {
            'use_vsids': True,
            'use_phase_saving': True,
            'use_clause_learning': True,
            'var_decay': 0.95,
            'clause_decay': 0.999,  # accepted for compatibility; clauses are never deleted
            'restart_interval': 100,
            'max_conflicts': 10000,
            'random_seed': 42
        }
        if config:
            self.config.update(config)

        self._rng = random.Random(self.config['random_seed'])
        self._queue: deque = deque()  # literals assigned true, not yet propagated
        self._flipped: List[bool] = []  # DPLL mode: was the decision at level i+1 already flipped?
        self._restart_limit = max(1, int(self.config['restart_interval']))
        self._conflicts_since_restart = 0
        self._conflicts = 0  # conflicts in this solver (max_conflicts applies to these)
        self._unsat_at_root = False
        self.clauses: List[List[int]] = []  # normalized clauses: originals, then learned
        self.num_original = 0
        self.learned: List[int] = []  # indices into self.clauses of learned clauses, in order
        self._load_clauses()
        self._initialize_watches()

    # ------------------------------------------------------------------ setup

    def _load_clauses(self):
        """Normalize the input: drop duplicate literals and tautologies, check ranges."""
        n = self.cnf.num_vars
        for clause in self.cnf.clauses:
            lits: List[int] = []
            seen: Set[int] = set()
            tautology = False
            for lit in clause.literals:
                v = lit.var
                if v == 0 or abs(v) > n:
                    raise ValueError(f"literal {v} out of range for {n} variables")
                if -v in seen:
                    tautology = True
                    break
                if v not in seen:
                    seen.add(v)
                    lits.append(v)
            if tautology:
                continue
            if not lits:
                self._unsat_at_root = True
            self.clauses.append(lits)
        self.num_original = len(self.clauses)

    def _initialize_watches(self):
        """Watch the first two literals of every clause with at least two literals."""
        for idx, lits in enumerate(self.clauses):
            if len(lits) >= 2:
                self._watch(idx, lits[0])
                self._watch(idx, lits[1])

    def _watch(self, idx: int, lit: int):
        self.watches.watches[lit].add(idx)

    def _unwatch(self, idx: int, lit: int):
        self.watches.watches[lit].discard(idx)

    def _value(self, lit: int) -> Optional[bool]:
        v = self.assignment.get(abs(lit))
        if v is None:
            return None
        return v if lit > 0 else not v

    # ------------------------------------------------------------------ search

    def solve(self) -> Tuple[SATResult, Optional[Dict[int, bool]]]:
        """Decide the formula. Returns (SATISFIABLE, model), (UNSATISFIABLE, None)
        or (TIMEOUT, None) once more than ``max_conflicts`` conflicts occurred."""
        logger.debug(f"Starting SAT solver for {self.cnf.num_vars} variables, {len(self.cnf.clauses)} clauses")
        self._backtrack(0)
        if self._unsat_at_root:
            return SATResult.UNSATISFIABLE, None

        # Unit clauses (original and learned) are not watched; assign them at level 0.
        for idx, lits in enumerate(self.clauses):
            if len(lits) == 1:
                val = self._value(lits[0])
                if val is False:
                    self._unsat_at_root = True
                    return SATResult.UNSATISFIABLE, None
                if val is None:
                    self._assign(abs(lits[0]), lits[0] > 0, idx)

        learning = self.config['use_clause_learning']
        while True:
            conflict = self._propagate()
            if conflict is not None:
                self.cnf.stats['conflicts'] += 1
                self._conflicts += 1
                self._conflicts_since_restart += 1
                if self.decision_level == 0:
                    self._unsat_at_root = True
                    logger.debug(f"UNSAT. Stats: {self.cnf.stats}")
                    return SATResult.UNSATISFIABLE, None
                if self._conflicts > self.config['max_conflicts']:
                    logger.warning("Timeout: max conflicts reached")
                    self._backtrack(0)
                    return SATResult.TIMEOUT, None
                if learning:
                    learned_clause, backtrack_level = self._analyze_conflict(conflict)
                    self._backtrack(backtrack_level)
                    self._add_learned(learned_clause)
                    if self.config['use_vsids']:
                        self._decay_activities()
                else:
                    if not self._flip_last_decision():
                        self._unsat_at_root = True
                        return SATResult.UNSATISFIABLE, None
                continue

            if learning and self._conflicts_since_restart >= self._restart_limit:
                self._restart()
                continue

            var = self._choose_branching_variable()
            if var is None:
                model = self.assignment.copy()
                if not all(any((model[abs(l)] if l > 0 else not model[abs(l)]) for l in c)
                           for c in self.clauses[:self.num_original]):
                    raise RuntimeError("internal error: model does not satisfy the formula")
                logger.debug(f"SAT. Stats: {self.cnf.stats}")
                return SATResult.SATISFIABLE, model

            self.decision_level += 1
            self.trail_lim.append(len(self.trail))
            self._flipped.append(False)
            self._assign(var, self._get_phase(var), None)
            self.cnf.stats['decisions'] += 1

    def _propagate(self) -> Optional[int]:
        """Unit propagation with two watched literals.

        Returns the index of a falsified clause, or None when the queue empties
        without a conflict. Invariant: clause[0] and clause[1] are its watches."""
        while self._queue:
            p = self._queue.popleft()  # p just became true
            false_lit = -p
            for idx in list(self.watches.watches[false_lit]):
                lits = self.clauses[idx]
                if lits[0] == false_lit:
                    lits[0], lits[1] = lits[1], lits[0]
                if self._value(lits[0]) is True:
                    continue
                new_watch = self._find_new_watch(lits, false_lit)
                if new_watch is not None:
                    k = lits.index(new_watch, 2)
                    lits[1], lits[k] = lits[k], lits[1]
                    self._unwatch(idx, false_lit)
                    self._watch(idx, new_watch)
                    continue
                first = self._value(lits[0])
                if first is False:
                    self._queue.clear()
                    return idx
                self._assign(abs(lits[0]), lits[0] > 0, idx)
        return None

    def _find_new_watch(self, clause, old_watch) -> Optional[int]:
        """Return a literal of ``clause`` (a normalized list of ints, positions 2 and
        later) that is not false and could replace ``old_watch``, or None."""
        for lit in clause[2:]:
            if self._value(lit) is not False:
                return lit
        return None

    def _propagate_queue(self) -> bool:
        """True when assigned literals are still waiting to be propagated."""
        return bool(self._queue)

    def _assign(self, var: int, value: bool, reason: Optional[int]):
        """Assign a variable at the current decision level and queue it for propagation."""
        self.assignment[var] = value
        self.trail.append((var, value))
        self.reason[var] = reason
        self.cnf.var_states[var].decision_level = self.decision_level
        self.cnf.var_states[var].antecedent = reason
        self.cnf.stats['propagations'] += 1
        if self.config['use_phase_saving']:
            self.cnf.var_states[var].phase_saving = value
        self._queue.append(var if value else -var)

    def _backtrack(self, level: int):
        """Undo every assignment above decision level ``level``."""
        if level < 0:
            level = 0
        if self.decision_level > level:
            limit = self.trail_lim[level]
            while len(self.trail) > limit:
                var, _ = self.trail.pop()
                del self.assignment[var]
                del self.reason[var]
                self.cnf.var_states[var].decision_level = -1
                self.cnf.var_states[var].antecedent = None
            del self.trail_lim[level:]
            del self._flipped[level:]
            self.decision_level = level
        self._queue.clear()

    def _restart(self):
        """Restart search while keeping learned clauses. The interval grows by 1.5x
        after every restart, which keeps the search complete."""
        self._backtrack(0)
        self.cnf.stats['restarts'] += 1
        self._conflicts_since_restart = 0
        self._restart_limit = int(self._restart_limit * 1.5) + 1

    def _flip_last_decision(self) -> bool:
        """DPLL mode: backtrack to the deepest decision not yet flipped and assert its
        negation as a flipped decision at the same level. False when none is left."""
        level = self.decision_level
        while level > 0 and self._flipped[level - 1]:
            level -= 1
        if level == 0:
            return False
        var, value = self.trail[self.trail_lim[level - 1]]
        self._backtrack(level - 1)
        self.decision_level += 1
        self.trail_lim.append(len(self.trail))
        self._flipped.append(True)
        self._assign(var, not value, None)
        return True

    def _choose_branching_variable(self) -> Optional[int]:
        """Unassigned variable with the highest activity (ties: lowest index),
        or a random unassigned variable when use_vsids is False."""
        unassigned = [v for v in range(1, self.cnf.num_vars + 1)
                      if v not in self.assignment]
        if not unassigned:
            return None
        if self.config['use_vsids']:
            return max(unassigned, key=lambda v: self.cnf.var_states[v].activity)
        return self._rng.choice(unassigned)

    def _get_phase(self, var: int) -> bool:
        """Saved phase when phase saving is on and a phase exists, else False."""
        if self.config['use_phase_saving']:
            saved = self.cnf.var_states[var].phase_saving
            if saved is not None:
                return saved
        return False

    def _analyze_conflict(self, conflict_clause_idx: int) -> Tuple[Optional[Clause], int]:
        """First-UIP conflict analysis.

        Resolves the conflict clause with the reasons of current-level literals,
        in reverse trail order, until one current-level literal (the UIP) remains.
        The result is implied by the clause database. Returns (learned clause with
        the asserting literal first, level to backtrack to)."""
        if self.decision_level == 0:
            return None, -1
        seen: Set[int] = set()
        learned: List[int] = [0]
        counter = 0
        index = len(self.trail) - 1
        clause = self.clauses[conflict_clause_idx]
        pivot_var = 0
        while True:
            for lit in clause:
                v = abs(lit)
                if v == pivot_var or v in seen:
                    continue
                level = self.cnf.var_states[v].decision_level
                if level == 0:
                    continue
                seen.add(v)
                if self.config['use_vsids']:
                    self.cnf.var_states[v].activity += 1.0
                if level == self.decision_level:
                    counter += 1
                else:
                    learned.append(lit)
            while self.trail[index][0] not in seen:
                index -= 1
            pivot_var, value = self.trail[index]
            index -= 1
            counter -= 1
            if counter == 0:
                break
            clause = self.clauses[self.reason[pivot_var]]
        learned[0] = -pivot_var if value else pivot_var
        backtrack_level = 0
        if len(learned) > 1:
            best = 1
            for i in range(2, len(learned)):
                if (self.cnf.var_states[abs(learned[i])].decision_level >
                        self.cnf.var_states[abs(learned[best])].decision_level):
                    best = i
            learned[1], learned[best] = learned[best], learned[1]
            backtrack_level = self.cnf.var_states[abs(learned[1])].decision_level
        return Clause([Literal(l) for l in learned], learned=True), backtrack_level

    def _add_learned(self, learned_clause: Clause):
        """Store a learned clause (asserting literal first), watch it, and assert
        its first literal at the current (backtrack) level."""
        lits = [lit.var for lit in learned_clause.literals]
        idx = len(self.clauses)
        self.clauses.append(lits)
        self.learned.append(idx)
        self.cnf.stats['learned_clauses'] += 1
        if len(lits) >= 2:
            self._watch(idx, lits[0])
            self._watch(idx, lits[1])
        self._assign(abs(lits[0]), lits[0] > 0, idx)

    def _decay_activities(self):
        """Decay variable activities for VSIDS"""
        decay = self.config['var_decay']
        for var_state in self.cnf.var_states:
            var_state.activity *= decay

    def learned_clauses(self) -> List[List[int]]:
        """Learned clauses in the order they were derived (lists of signed ints)."""
        return [list(self.clauses[i]) for i in self.learned]

    def validate_solution(self) -> bool:
        """Validate that the current assignment satisfies all clauses"""
        for clause in self.cnf.clauses:
            if not clause.is_satisfied(self.assignment):
                return False
        return True

    def get_stats(self) -> Dict[str, Any]:
        """Get solver statistics"""
        return self.cnf.stats.copy()


class Visualizer:
    """Visualization utilities for SAT problems"""
    
    @staticmethod
    def generate_clause_heatmap(cnf: CNF, assignment: Optional[Dict[int, bool]] = None, 
                                filename: str = "sat_heatmap.ppm"):
        """Generate PPM heatmap of clause satisfaction"""
        import numpy as np
        
        # Create matrix: rows=clauses, cols=variables
        height = len(cnf.clauses)
        width = cnf.num_vars
        
        if height == 0 or width == 0:
            return
        
        # Scale for visibility
        scale = max(1, min(10, 1000 // max(height, width)))
        img_height = height * scale
        img_width = width * scale
        
        # Create image array
        img = np.zeros((img_height, img_width, 3), dtype=np.uint8)
        
        for i, clause in enumerate(cnf.clauses):
            for lit in clause.literals:
                var = lit.variable - 1  # 0-indexed
                if var < width:
                    # Color based on literal polarity and satisfaction
                    if assignment and var + 1 in assignment:
                        if clause.is_satisfied(assignment):
                            # Green for satisfied
                            color = [0, 255, 0]
                        else:
                            # Check if this literal is satisfied
                            lit_sat = (assignment[var + 1] == lit.is_positive)
                            if lit_sat:
                                # Light green for satisfied literal
                                color = [128, 255, 128]
                            else:
                                # Red for unsatisfied literal
                                color = [255, 0, 0]
                    else:
                        # Blue for unassigned
                        if lit.is_positive:
                            color = [0, 0, 255]
                        else:
                            color = [0, 0, 128]
                    
                    # Fill scaled rectangle
                    y_start = i * scale
                    y_end = (i + 1) * scale
                    x_start = var * scale
                    x_end = (var + 1) * scale
                    img[y_start:y_end, x_start:x_end] = color
        
        # Write PPM file
        with open(filename, 'wb') as f:
            f.write(f"P6\n{img_width} {img_height}\n255\n".encode())
            f.write(img.tobytes())
        
        logger.info(f"Generated visualization: {filename}")
    
    @staticmethod
    def generate_activity_map(solver: SATSolver, filename: str = "sat_activity.ppm"):
        """Generate PPM visualization of variable activities"""
        import numpy as np
        
        num_vars = solver.cnf.num_vars
        size = int(np.ceil(np.sqrt(num_vars)))
        scale = max(1, min(20, 500 // size))
        img_size = size * scale
        
        # Create image array
        img = np.zeros((img_size, img_size, 3), dtype=np.uint8)
        
        # Get max activity for normalization
        max_activity = max((state.activity for state in solver.cnf.var_states[1:]), 
                          default=1.0)
        
        for var in range(1, num_vars + 1):
            row = (var - 1) // size
            col = (var - 1) % size
            
            if row < size and col < size:
                activity = solver.cnf.var_states[var].activity
                intensity = int(255 * (activity / max_activity)) if max_activity > 0 else 0
                
                # Color based on assignment status
                if var in solver.assignment:
                    if solver.assignment[var]:
                        # Green channel for true
                        color = [0, intensity, 0]
                    else:
                        # Red channel for false
                        color = [intensity, 0, 0]
                else:
                    # Blue channel for unassigned
                    color = [0, 0, intensity]
                
                # Fill scaled rectangle
                y_start = row * scale
                y_end = (row + 1) * scale
                x_start = col * scale
                x_end = (col + 1) * scale
                img[y_start:y_end, x_start:x_end] = color
        
        # Write PPM file
        with open(filename, 'wb') as f:
            f.write(f"P6\n{img_size} {img_size}\n255\n".encode())
            f.write(img.tobytes())
        
        logger.info(f"Generated activity map: {filename}")


def solve_sat(cnf: CNF, config: Optional[Dict[str, Any]] = None) -> Tuple[SATResult, Optional[Dict[int, bool]]]:
    """Convenience function to solve a SAT problem"""
    solver = SATSolver(cnf, config)
    return solver.solve()


def main():
    """Example usage and testing"""
    # Create a simple SAT problem
    cnf = CNF(3)
    cnf.add_clause([1, -2])     # x1 ∨ ¬x2
    cnf.add_clause([-1, 2, 3])  # ¬x1 ∨ x2 ∨ x3
    cnf.add_clause([-3])        # ¬x3
    
    print("Solving CNF formula:")
    for i, clause in enumerate(cnf.clauses):
        print(f"  Clause {i}: {clause}")
    
    # Solve
    result, assignment = solve_sat(cnf)
    
    print(f"\nResult: {result.value}")
    if assignment:
        print("Assignment:")
        for var in sorted(assignment.keys()):
            print(f"  x{var} = {assignment[var]}")
    
    # Generate visualization
    if assignment:
        visualizer = Visualizer()
        visualizer.generate_clause_heatmap(cnf, assignment, "example_sat.ppm")
    
    # Test with a larger random problem
    print("\n" + "="*50)
    print("Testing with random 3-SAT problem...")
    
    # Generate random 3-SAT
    num_vars = 50
    num_clauses = 200
    cnf_random = CNF(num_vars)
    
    for _ in range(num_clauses):
        clause = random.sample(range(1, num_vars + 1), 3)
        literals = [v if random.random() > 0.5 else -v for v in clause]
        cnf_random.add_clause(literals)
    
    # Solve with configuration
    config = {
        'use_vsids': True,
        'use_clause_learning': True,
        'max_conflicts': 10000
    }
    
    start_time = time.time()
    result, assignment = solve_sat(cnf_random, config)
    solve_time = time.time() - start_time
    
    print(f"Result: {result.value}")
    print(f"Time: {solve_time:.3f} seconds")
    print(f"Stats: {cnf_random.stats}")
    
    if assignment:
        # Validate solution
        solver = SATSolver(cnf_random, config)
        solver.assignment = assignment
        is_valid = solver.validate_solution()
        print(f"Solution valid: {is_valid}")
        
        # Generate visualizations
        visualizer = Visualizer()
        visualizer.generate_clause_heatmap(cnf_random, assignment, "random_3sat.ppm")


if __name__ == "__main__":
    main()
