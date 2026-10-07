"""SAT.c: compile it with the system C compiler in a temporary directory
(together with tests/sat_c_driver.c) and check it against exhaustive search
for n <= 10, in CDCL and plain-DPLL modes. Every DRUP proof line (each
learned clause, and the empty clause on UNSAT) is checked to follow from the
formula plus the earlier lines by unit propagation. Skipped when no C
compiler is available. Extra compiler flags (for example sanitizers) can be
passed in SAT_C_CFLAGS."""

import os
import random
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT))

from test_sat_py import brute, random_cnf, rup, satisfies  # noqa: E402


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
    build = tmp_path_factory.mktemp("sat_c")
    exe = build / "sat_c_driver"
    extra = shlex.split(os.environ.get("SAT_C_CFLAGS", ""))
    cmd = [cc, "-std=c99", "-O2", "-Wall", "-DSAT_NO_MAIN", "-I", str(ROOT), *extra,
           str(ROOT / "SAT.c"), str(ROOT / "tests" / "sat_c_driver.c"), "-o", str(exe), "-lm"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return exe


def _run(driver, args, stdin, cwd=None):
    proc = subprocess.run([str(driver), *args], input=stdin, capture_output=True, text=True, cwd=cwd)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc.stdout


def _encode(instances):
    out = []
    for n, clauses in instances:
        out.append(f"p cnf {n} {len(clauses)}")
        out.extend(" ".join(map(str, c + [0])) for c in clauses)
    return "\n".join(out) + "\n"


def _parse(output):
    """Per instance: (status, model dict or None, proof clauses)."""
    results, proof, status = [], [], None
    for line in output.splitlines():
        if line.startswith("r "):
            lits = [int(x) for x in line[2:].split()]
            assert lits[-1] == 0, line
            proof.append(lits[:-1])
        elif line.startswith("s "):
            status = line[2:]
            if status != "SATISFIABLE":
                results.append((status, None, proof))
                proof = []
        elif line.startswith("v "):
            lits = [int(x) for x in line[2:].split()][:-1]
            results.append((status, {abs(l): l > 0 for l in lits}, proof))
            proof = []
        else:
            raise AssertionError(f"unexpected driver output: {line!r}")
    return results


def solve_batch(driver, instances, mode="cdcl", restart=100, proof=True):
    out = _run(driver, ["batch", mode, str(restart), "1" if proof else "0"], _encode(instances))
    results = _parse(out)
    assert len(results) == len(instances)
    return results


def check_batch(driver, instances, mode, restart=100):
    counts = {"SATISFIABLE": 0, "UNSATISFIABLE": 0}
    for (n, clauses), (status, model, proof) in zip(instances, solve_batch(driver, instances, mode, restart)):
        truth = brute(n, clauses)
        db = [list(c) for c in clauses]
        for lemma in proof:
            assert rup(db, lemma), (n, clauses, lemma)
            db.append(lemma)
        if truth is None:
            assert status == "UNSATISFIABLE", (n, clauses, status)
            assert proof and proof[-1] == [], (n, clauses, proof)
        else:
            assert status == "SATISFIABLE", (n, clauses, status)
            assert sorted(model) == list(range(1, n + 1))
            assert satisfies(clauses, model)
            assert [] not in proof
        counts[status] += 1
    return counts


def random_instances(seed, count):
    """Mostly random 3-SAT near the threshold (clause/variable ratio 3 to 6),
    plus mixed-width CNFs with unit and binary clauses."""
    rng = random.Random(seed)
    out = []
    for _ in range(count):
        n = rng.randint(1, 10)
        if n >= 3 and rng.random() < 0.75:
            m = max(1, round(rng.uniform(3.0, 6.0) * n))
            clauses = [[v if rng.random() < 0.5 else -v for v in rng.sample(range(1, n + 1), 3)]
                       for _ in range(m)]
        else:
            clauses = random_cnf(rng, n, rng.randint(1, 5 * n), 3 if rng.random() < 0.7 else 5)
        out.append((n, clauses))
    return out


def test_api(driver, tmp_path):
    out = _run(driver, ["api"], "", cwd=tmp_path)
    assert "FAIL" not in out and out.strip().endswith("API OK"), out


def test_cdcl_random_against_brute_force(driver):
    counts = check_batch(driver, random_instances(20261006, 600), "cdcl", restart=100)
    assert counts["SATISFIABLE"] >= 100 and counts["UNSATISFIABLE"] >= 100, counts


def test_cdcl_frequent_restarts(driver):
    counts = check_batch(driver, random_instances(7, 200), "cdcl", restart=1)
    assert min(counts.values()) >= 20, counts


def test_dpll_random_against_brute_force(driver):
    counts = check_batch(driver, random_instances(42, 300), "dpll")
    assert min(counts.values()) >= 50, counts


def test_edge_cases(driver):
    instances = [
        (0, []),
        (1, [[]]),
        (3, [[1, 2], []]),
        (1, [[1], [-1]]),
        (2, [[1, 1, -2], [2, -2], [-1, -1]]),
        (3, [[1, -1], [2, -2, 3]]),
        (2, [[1, 2], [1, -2], [-1, 2], [-1, -2]]),
        (10, []),
    ]
    for mode in ("cdcl", "dpll"):
        check_batch(driver, instances, mode)


def test_parse_string(driver):
    sat = "c example\np cnf 3 2\n1 -2\n 0 2 3 0\n"
    unsat = "p cnf 1 2\n1 0\n-1 0\n%\n0\n"
    assert _run(driver, ["string", "cdcl"], sat).startswith("s SATISFIABLE")
    assert _run(driver, ["string", "dpll"], unsat).strip() == "s UNSATISFIABLE"
    assert _run(driver, ["string", "cdcl"], "p cnf 1 1\n2 0\n").strip() == "s PARSE_ERROR"
    assert _run(driver, ["string", "cdcl"], "1 0\n").strip() == "s PARSE_ERROR"


def test_larger_random_3sat_agrees_with_sat_py(driver):
    from SAT import CNF, SATResult, SATSolver

    rng = random.Random(4)
    instances = []
    for _ in range(20):
        n = 40
        clauses = [[v if rng.random() < 0.5 else -v for v in rng.sample(range(1, n + 1), 3)]
                   for _ in range(int(4.26 * n))]
        instances.append((n, clauses))
    for mode in ("cdcl", "dpll"):
        for (n, clauses), (status, model, proof) in zip(instances, solve_batch(driver, instances, mode)):
            cnf = CNF(n)
            for c in clauses:
                cnf.add_clause(c)
            expected, _ = SATSolver(cnf).solve()
            if expected is SATResult.SATISFIABLE:
                assert status == "SATISFIABLE" and satisfies(clauses, model)
            else:
                assert status == "UNSATISFIABLE" and proof[-1] == []
