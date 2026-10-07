"""Brute-force check of the GF(2) XOR-SAT solver for n <= 10."""

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from xor_sat import pack, solve_xorsat, verifies, verify_certificate


def count_solutions(n, equations):
    """Enumerate all 2^n assignments; return (count, first solution or None)."""
    rows = [pack(n, vs, b) for vs, b in equations]
    mask = (1 << n) - 1
    count = 0
    first = None
    for x in range(1 << n):
        if all(bin(row & mask & x).count("1") & 1 == row >> n & 1 for row in rows):
            count += 1
            if first is None:
                first = [((x >> i) & 1) == 1 for i in range(n)]
    return count, first


def random_equation(n, rng):
    k = rng.randint(1, n)
    vs = rng.sample(range(1, n + 1), k)
    if rng.random() < 0.2:
        vs.append(rng.choice(vs))  # repeated variable must cancel
    return vs, rng.randint(0, 1)


def random_system(n, m, rng, kind):
    if kind == "planted":
        secret = [rng.random() < 0.5 for _ in range(n)]
        equations = []
        for _ in range(m):
            vs, _ = random_equation(n, rng)
            b = 0
            for v in vs:
                b ^= int(secret[v - 1])
            equations.append((vs, b))
        return equations
    equations = [random_equation(n, rng) for _ in range(m)]
    if kind == "forced_unsat" and equations:
        # XOR of a random subset with the rhs flipped: contradicts the subset.
        subset = rng.sample(range(len(equations)), rng.randint(1, len(equations)))
        vs, b = [], 1
        for j in subset:
            vs.extend(equations[j][0])
            b ^= equations[j][1]
        equations.insert(rng.randrange(len(equations) + 1), (vs or [1, 1], b))
    return equations


def check(n, equations):
    solved = solve_xorsat(n, equations)
    count, first = count_solutions(n, equations)
    assert solved["sat"] == (count > 0), (n, equations, solved)
    if solved["sat"]:
        assert verifies(n, equations, solved["assignment"])
        assert solved["certificate"] is None
        # An affine solution space has exactly 2^(n - rank) points.
        assert count == 1 << (n - solved["rank"])
    else:
        assert solved["assignment"] is None
        assert verify_certificate(n, equations, solved["certificate"])
    assert solved["rank"] == len(solved["pivots"]) <= min(n, len(equations))
    assert solved["ops"] >= solved["row_xors"] >= 0
    return solved


def test_against_brute():
    rng = random.Random(2026)
    seen = {"sat": 0, "unsat": 0}
    for n in range(1, 11):
        for m in (1, n // 2 + 1, n, n + 2, 2 * n + 3):
            for kind in ("planted", "random", "forced_unsat"):
                for _ in range(8):
                    solved = check(n, random_system(n, m, rng, kind))
                    seen["sat" if solved["sat"] else "unsat"] += 1
                    if kind == "planted":
                        assert solved["sat"]
                    if kind == "forced_unsat":
                        assert not solved["sat"]
    assert seen["sat"] > 100 and seen["unsat"] > 100, seen


def test_edge_cases():
    assert solve_xorsat(0, [])["sat"] is True
    assert solve_xorsat(3, [])["assignment"] == [False, False, False]
    empty_one = solve_xorsat(2, [([], 1)])
    assert empty_one["sat"] is False and empty_one["certificate"] == [0]
    cancels = solve_xorsat(2, [([1, 1], 1)])
    assert cancels["sat"] is False and cancels["certificate"] == [0]
    assert solve_xorsat(2, [([1, 1, 2], 1)])["assignment"][1] is True


def test_explicit_unsat_certificate():
    # x1^x2=1, x2^x3=1, x1^x3=1 sums to 0=1.
    eqs = [([1, 2], 1), ([2, 3], 1), ([1, 3], 1), ([1], 0)]
    solved = solve_xorsat(3, eqs)
    assert solved["sat"] is False
    assert verify_certificate(3, eqs, solved["certificate"])
    assert set(solved["certificate"]) == {0, 1, 2}


def test_certificate_verifier_rejects_bogus():
    eqs = [([1, 2], 1), ([2, 3], 1), ([1, 3], 1)]
    assert verify_certificate(3, eqs, [0, 1, 2])
    assert not verify_certificate(3, eqs, [])
    assert not verify_certificate(3, eqs, [0, 1])
    assert not verify_certificate(3, eqs, [0, 0, 1, 2])
    assert not verify_certificate(3, eqs, [0, 1, 5])
    consistent = [([1, 2], 1), ([2, 3], 0)]
    for subset in ([0], [1], [0, 1]):
        assert not verify_certificate(3, consistent, subset)


def test_unique_solution():
    rng = random.Random(5)
    n = 10
    secret = [rng.random() < 0.5 for _ in range(n)]
    eqs = [([i + 1], int(secret[i])) for i in range(n)]
    solved = solve_xorsat(n, eqs)
    assert solved["assignment"] == secret and solved["rank"] == n


if __name__ == "__main__":
    test_against_brute()
    test_edge_cases()
    test_explicit_unsat_certificate()
    test_certificate_verifier_rejects_bogus()
    test_unique_solution()
    print("ok")
