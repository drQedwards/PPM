"""Brute-force check of the linear 2-SAT solver for n <= 10."""

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from two_sat import solve_2sat, verifies


def brute(n, clauses):
    for mask in range(1 << n):
        assignment = [((mask >> i) & 1) == 1 for i in range(n)]
        if verifies(n, clauses, assignment):
            return assignment
    return None


def random_formula(n, m, rng, planted):
    secret = [rng.random() < 0.5 for _ in range(n)]
    clauses = []
    while len(clauses) < m:
        a = rng.randrange(1, n + 1)
        b = rng.randrange(1, n + 1)
        if n > 1:
            while b == a:
                b = rng.randrange(1, n + 1)
        left = a if rng.random() < 0.5 else -a
        right = b if rng.random() < 0.5 else -b
        if planted:
            holds = ((left > 0) == secret[abs(left) - 1]) or (
                (right > 0) == secret[abs(right) - 1]
            )
            if not holds:
                left = a if secret[a - 1] else -a
        clauses.append((left, right))
    return clauses


def test_against_brute():
    rng = random.Random(7)
    for n in (1, 2, 4, 6, 8, 10):
        for _ in range(20):
            for planted in (True, False):
                m = max(1, int((2.2 if planted else 1.3) * n))
                clauses = random_formula(n, m, rng, planted)
                solved = solve_2sat(n, clauses)
                truth = brute(n, clauses)
                assert solved["sat"] == (truth is not None)
                if solved["sat"]:
                    assert verifies(n, clauses, solved["assignment"])


def test_explicit_unsat():
    solved = solve_2sat(2, [(1, 2), (1, -2), (-1, 2), (-1, -2)])
    assert solved["sat"] is False
    assert solved["conflict"] == 0


if __name__ == "__main__":
    test_against_brute()
    test_explicit_unsat()
    print("ok")
