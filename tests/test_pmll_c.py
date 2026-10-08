"""PMLL.c SAT refine loop: compile PMLL.c (with -DPMLL_NO_MAIN) and
tests/pmll_c_driver.c, then check pml_logic_loop against exhaustive search.

Covers the review findings on the old loop: it never backtracked an earlier
decision, marked contradictory unit clauses as solved, marked a step-limit
timeout as solved, and read assignment[-1] for a 0 literal. Skipped when no C
compiler is available. Extra compiler flags (for example sanitizers) can be
passed in PMLL_C_CFLAGS."""

import itertools
import os
import random
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PML_UNRESOLVED, PML_SAT, PML_UNSAT = 0, 1, 2
INT_MIN = -(2 ** 31)


def _compiler():
    for cand in (os.environ.get("CC"), "cc", "gcc", "clang"):
        if cand and shutil.which(cand):
            return cand
    return None


@pytest.fixture(scope="module")
def driver(tmp_path_factory):
    cc = _compiler()
    if cc is None:
        pytest.skip("no C compiler")
    build = tmp_path_factory.mktemp("pmll_c")
    exe = build / "pmll_c_driver"
    extra = shlex.split(os.environ.get("PMLL_C_CFLAGS", ""))
    cmd = [cc, "-std=c99", "-O2", "-Wall", "-DPMLL_NO_MAIN", "-I", str(ROOT), *extra,
           str(ROOT / "PMLL.c"), str(ROOT / "tests" / "pmll_c_driver.c"), "-o", str(exe), "-lm"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return exe


def _encode(instances):
    out = []
    for n, clauses in instances:
        out.append(f"p cnf {n} {len(clauses)}")
        for c in clauses:
            if any(lit == 0 or lit == INT_MIN or abs(lit) > n for lit in c):
                out.append("x " + " ".join(map(str, [len(c), *c])))
            else:
                out.append(" ".join(map(str, [*c, 0])))
    return "\n".join(out) + "\n"


def _solve(driver, instances):
    proc = subprocess.run([str(driver)], input=_encode(instances), capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    rows = [line.split() for line in proc.stderr.splitlines() if line.startswith("R ")]
    assert len(rows) == len(instances), proc.stderr
    return [(int(r[1]), [int(x) for x in r[2:]]) for r in rows]


def _valid(lit, n):
    return lit != 0 and lit != INT_MIN and abs(lit) <= n


def _satisfies(n, clauses, assignment):
    return all(any(_valid(l, n) and assignment[abs(l) - 1] == (1 if l > 0 else 0) for l in c)
               for c in clauses)


def _brute(n, clauses):
    return any(_satisfies(n, clauses, bits) for bits in itertools.product((0, 1), repeat=n))


def test_backtracks_an_earlier_decision(driver):
    # (x1 | x2) & (x1 | ~x2): the old loop fixed x1=0 and never flipped it.
    [(flag, a)] = _solve(driver, [(2, [[1, 2], [1, -2]])])
    assert flag == PML_SAT and a[0] == 1


def test_contradictory_units_are_unsat(driver):
    [(flag, a)] = _solve(driver, [(1, [[1], [-1]])])
    assert flag == PML_UNSAT and a == [-1]


def test_unsat_is_not_reported_solved(driver):
    # All four 2-clauses over x1, x2: unsatisfiable.
    [(flag, _)] = _solve(driver, [(2, [[1, 2], [1, -2], [-1, 2], [-1, -2]])])
    assert flag == PML_UNSAT


def test_invalid_literals_are_ignored(driver):
    res = _solve(driver, [
        (2, [[0, 1], [INT_MIN, -2]]),      # SAT via x1=1, x2=0
        (1, [[0], [INT_MIN]]),             # no valid literal at all: UNSAT
        (2, [[5, -1], [1]]),               # x5 is out of range: UNSAT
    ])
    assert res[0][0] == PML_SAT and res[0][1] == [1, 0]
    assert res[1][0] == PML_UNSAT
    assert res[2][0] == PML_UNSAT


def test_matches_brute_force(driver):
    rng = random.Random(20261008)
    instances = []
    for _ in range(600):
        n = rng.randint(1, 8)
        m = rng.randint(1, 4 * n)
        clauses = []
        for _ in range(m):
            k = rng.randint(1, 3)
            clauses.append([rng.choice((-1, 1)) * rng.randint(1, n) for _ in range(k)])
        instances.append((n, clauses))
    results = _solve(driver, instances)
    n_sat = 0
    for (n, clauses), (flag, a) in zip(instances, results):
        expect = _brute(n, clauses)
        assert flag in (PML_SAT, PML_UNSAT), (n, clauses, flag)
        assert (flag == PML_SAT) == expect, (n, clauses, flag)
        if flag == PML_SAT:
            n_sat += 1
            assert -1 not in a and _satisfies(n, clauses, a), (n, clauses, a)
    assert 0 < n_sat < len(instances)
