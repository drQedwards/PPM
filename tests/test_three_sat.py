"""Brute-force check of the exact 3-SAT decider."""

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from three_sat import UNSAT_CORE, solve_3sat, verifies


def brute(n, clauses):
    for mask in range(1 << n):
        assignment = [((mask >> i) & 1) == 1 for i in range(n)]
        if verifies(n, clauses, assignment):
            return assignment
    return None


def random_3cnf(n, m, rng, planted):
    secret = [rng.random() < 0.5 for _ in range(n)]
    clauses = []
    while len(clauses) < m:
        chosen = []
        while len(chosen) < min(3, n):
            v = rng.randrange(1, n + 1)
            if v not in chosen:
                chosen.append(v)
        lits = [v if rng.random() < 0.5 else -v for v in chosen]
        if planted:
            holds = any((lit > 0) == secret[abs(lit) - 1] for lit in lits)
            if not holds:
                i = rng.randrange(len(lits))
                v = abs(lits[i])
                lits[i] = v if secret[v - 1] else -v
        clauses.append(lits)
    return clauses


def test_against_brute():
    rng = random.Random(11)
    for n in (1, 2, 3, 5, 8, 10):
        for _ in range(12):
            for planted in (True, False):
                m = max(1, int((3.5 if planted else 2.0) * n))
                clauses = random_3cnf(n, m, rng, planted)
                solved = solve_3sat(n, clauses)
                truth = brute(n, clauses)
                assert solved["sat"] == (truth is not None), (n, clauses, solved["sat"])
                if solved["sat"]:
                    assert verifies(n, clauses, solved["assignment"])


def test_unsat_core():
    solved = solve_3sat(3, UNSAT_CORE)
    assert solved["sat"] is False
    assert brute(3, UNSAT_CORE) is None


def test_empty_formula():
    solved = solve_3sat(4, [])
    assert solved["sat"] is True
    assert verifies(4, [], solved["assignment"])


if __name__ == "__main__":
    test_against_brute()
    test_unsat_core()
    test_empty_formula()
    print("ok")
