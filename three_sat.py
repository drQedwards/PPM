"""Exact 3-SAT decision procedure.

DPLL with unit propagation. Every finite 3-CNF gets an answer: satisfiable,
with a witness, or unsatisfiable, after the search tree is exhausted.

The number of steps is not bounded by any polynomial this file can justify.
3-SAT is NP-complete. This procedure does not place it in P, and it does not
resolve P versus NP.
"""

from __future__ import annotations


def _lit_value(assign, lit):
    current = assign[abs(lit)]
    if current == 0:
        return 0
    want = 1 if lit > 0 else -1
    return 1 if current == want else -1


def solve_3sat(n, clauses):
    for clause in clauses:
        if len(clause) == 0 or len(clause) > 3:
            raise ValueError("each clause must contain 1, 2, or 3 literals")
        for lit in clause:
            if lit == 0 or abs(lit) > n:
                raise ValueError("literal out of range")

    assign = [0] * (n + 1)
    trail = []
    nodes = 0
    decisions = 0
    units = 0
    conflicts = 0

    def set_lit(lit):
        assign[abs(lit)] = 1 if lit > 0 else -1
        trail.append(lit)

    def undo_to(checkpoint):
        while len(trail) > checkpoint:
            assign[abs(trail.pop())] = 0

    def unit_propagate():
        nonlocal units
        changed = True
        while changed:
            changed = False
            for clause in clauses:
                satisfied = False
                open_count = 0
                open_lit = 0
                for lit in clause:
                    value = _lit_value(assign, lit)
                    if value == 1:
                        satisfied = True
                        break
                    if value == 0:
                        open_count += 1
                        open_lit = lit
                if satisfied:
                    continue
                if open_count == 0:
                    return False
                if open_count == 1:
                    set_lit(open_lit)
                    units += 1
                    changed = True
        return True

    def satisfied():
        return all(any(_lit_value(assign, lit) == 1 for lit in clause) for clause in clauses)

    def pick():
        count = [0] * (n + 1)
        for clause in clauses:
            clause_sat = False
            open_vars = []
            for lit in clause:
                value = _lit_value(assign, lit)
                if value == 1:
                    clause_sat = True
                    break
                if value == 0:
                    open_vars.append(abs(lit))
            if clause_sat:
                continue
            for variable in open_vars:
                count[variable] += 1
        best = 0
        best_count = -1
        for variable in range(1, n + 1):
            if assign[variable] != 0:
                continue
            if count[variable] > best_count:
                best = variable
                best_count = count[variable]
        return best

    def pack(sat):
        assignment = None
        if sat:
            assignment = [assign[variable] == 1 for variable in range(1, n + 1)]
        return {
            "sat": sat,
            "assignment": assignment,
            "nodes": nodes,
            "decisions": decisions,
            "units": units,
            "conflicts": conflicts,
        }

    if not unit_propagate():
        conflicts += 1
        return pack(False)

    stack = []
    while True:
        nodes += 1
        if satisfied():
            return pack(True)
        variable = pick()
        if variable == 0:
            return pack(True)
        decisions += 1
        checkpoint = len(trail)
        stack.append({"lit": variable, "flipped": False, "checkpoint": checkpoint})
        set_lit(variable)
        while not unit_propagate():
            conflicts += 1
            flipped = False
            while stack:
                frame = stack[-1]
                undo_to(frame["checkpoint"])
                if not frame["flipped"]:
                    frame["flipped"] = True
                    set_lit(-frame["lit"])
                    flipped = True
                    break
                stack.pop()
            if not flipped:
                return pack(False)


def verifies(n, clauses, assignment):
    del n
    for clause in clauses:
        ok = False
        for lit in clause:
            value = assignment[lit - 1] if lit > 0 else (not assignment[-lit - 1])
            if value:
                ok = True
                break
        if not ok:
            return False
    return True


UNSAT_CORE = [
    [1, 2, 3],
    [1, 2, -3],
    [1, -2, 3],
    [1, -2, -3],
    [-1, 2, 3],
    [-1, 2, -3],
    [-1, -2, 3],
    [-1, -2, -3],
]
