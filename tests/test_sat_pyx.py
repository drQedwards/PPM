"""SAT.pyx: build it with Cython in a temporary directory and check it against
exhaustive search for n <= 10. Skipped when Cython, setuptools, the Python
headers or a C compiler are not available."""

import importlib.util
import os
import random
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_sat_py import brute, random_cnf, rup, satisfies  # noqa: E402


def _missing_toolchain():
    for mod in ("Cython", "setuptools"):
        if importlib.util.find_spec(mod) is None:
            return f"{mod} is not installed"
    include = sysconfig.get_paths().get("include") or ""
    if not (Path(include) / "Python.h").exists():
        return "Python headers (Python.h) are not installed"
    if not (shutil.which(os.environ.get("CC", "cc")) or shutil.which("gcc") or shutil.which("clang")):
        return "no C compiler"
    return None


@pytest.fixture(scope="module")
def satx(tmp_path_factory):
    reason = _missing_toolchain()
    if reason:
        pytest.skip(f"cannot build SAT.pyx: {reason}")
    build = tmp_path_factory.mktemp("sat_pyx")
    shutil.copy(ROOT / "SAT.pyx", build / "SAT.pyx")
    proc = subprocess.run([sys.executable, "-m", "Cython.Build.Cythonize", "-i", "-3", "SAT.pyx"],
                          cwd=build, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    so = next(p for p in build.iterdir() if p.name.startswith("SAT.") and p.suffix in (".so", ".pyd"))
    spec = importlib.util.spec_from_file_location("SAT", so)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run(satx, n, clauses, **config):
    s = satx.CythonSATSolver(n)
    for key, val in config.items():
        setattr(s, key, val)
    for c in clauses:
        s.add_clause(list(c))
    result, model = s.solve()
    truth = brute(n, clauses)
    if truth is None:
        assert result == satx.UNSAT and model is None, (n, clauses, result)
    else:
        assert result == satx.SAT, (n, clauses, result)
        assert sorted(model) == list(range(1, n + 1))
        assert satisfies(clauses, model) and s.validate(model)
    db = [list(c) for c in clauses]
    for lemma in s.learned_clauses():
        assert rup(db, lemma), (clauses, lemma)
        db.append(lemma)
    return result


def test_against_brute_force(satx):
    rng = random.Random(20261007)
    counts = {satx.SAT: 0, satx.UNSAT: 0}
    configs = [{}, {"restart_interval": 2}, {"use_clause_learning": False},
               {"use_vsids": False, "use_phase_saving": False}]
    for n in range(1, 11):
        for _ in range(30):
            ratio = rng.choice([2.0, 3.5, 4.3, 5.5, 7.0])
            clauses = random_cnf(rng, n, max(1, int(ratio * n)), 3)
            for config in configs:
                counts[run(satx, n, clauses, **config)] += 1
    assert counts[satx.SAT] > 100 and counts[satx.UNSAT] > 100


def test_wider_clauses(satx):
    rng = random.Random(7)
    for n in range(4, 11):
        for _ in range(15):
            clauses = random_cnf(rng, n, rng.randint(n, 12 * n), 5)
            run(satx, n, clauses)
            run(satx, n, clauses, use_clause_learning=False)


def test_edge_cases_and_wrapper(satx, tmp_path):
    all_signs = [[a * 1, b * 2, c * 3] for a in (1, -1) for b in (1, -1) for c in (1, -1)]
    assert run(satx, 3, all_signs) == satx.UNSAT
    assert run(satx, 4, []) == satx.SAT
    assert run(satx, 2, [[1], [-1]]) == satx.UNSAT
    assert run(satx, 3, [[1, 1, -2], [2, 2], [-1, 3, 3]]) == satx.SAT
    assert run(satx, 2, [[1, -1], [2]]) == satx.SAT
    s = satx.CythonSATSolver(2)
    s.add_clause([])
    assert s.solve() == (satx.UNSAT, None)
    with pytest.raises(ValueError):
        satx.CythonSATSolver(1).add_clause([2])

    w = satx.PySATSolver(3, {"use_clause_learning": False, "max_conflicts": 50})
    for c in ([1, 2], [-1, 3], [-3]):
        w.add_clause(c)
    status, model = w.solve()
    assert status == "SAT" and w.validate(model) and model[3] is False
    assert w.get_stats()["decisions"] >= 0
    w.visualize(str(tmp_path / "v.ppm"), model)
    assert (tmp_path / "v.ppm").read_bytes().startswith(b"P6\n")

    path = tmp_path / "f.cnf"
    path.write_text("c x\np cnf 3 3\n1 -2\n 0 2 3 0\n-1 -3 0\n")
    status, model = satx.PySATSolver.from_dimacs(str(path)).solve()
    assert status == "SAT" and satisfies([[1, -2], [2, 3], [-1, -3]], model)


def test_timeout_and_resolve(satx):
    p, h = 7, 6
    var = lambda i, j: i * h + j + 1
    clauses = [[var(i, j) for j in range(h)] for i in range(p)]
    clauses += [[-var(i, j), -var(k, j)] for j in range(h) for i in range(p) for k in range(i + 1, p)]
    s = satx.CythonSATSolver(p * h)
    for c in clauses:
        s.add_clause(c)
    s.max_conflicts = 5
    assert s.solve() == (satx.TIMEOUT, None)
    s.max_conflicts = 1000000
    assert s.solve() == (satx.UNSAT, None)


def test_matches_sat_py_on_larger_random_3sat(satx):
    import SAT as satpy
    rng = random.Random(5)
    for n in (20, 30, 40):
        for _ in range(10):
            clauses = [[v if rng.random() < 0.5 else -v for v in rng.sample(range(1, n + 1), 3)]
                       for _ in range(round(4.26 * n))]
            cnf = satpy.CNF(n)
            for c in clauses:
                cnf.add_clause(c)
            py_result, _ = satpy.SATSolver(cnf).solve()
            s = satx.CythonSATSolver(n)
            for c in clauses:
                s.add_clause(c)
            result, model = s.solve()
            assert (result == satx.SAT) == (py_result is satpy.SATResult.SATISFIABLE)
            if model is not None:
                assert satisfies(clauses, model)
