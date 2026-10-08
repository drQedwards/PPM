"""Pypm.pyx: Cython binding over PMLL.c (silo, embeddings, pml_logic_loop).
Built in a temp dir; skipped when Cython / headers / a C compiler are missing."""
import importlib.util
import itertools
import os
import random
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def pypm(tmp_path_factory):
    for m in ("Cython", "setuptools"):
        if importlib.util.find_spec(m) is None:
            pytest.skip(f"{m} not installed")
    if not (Path(sysconfig.get_paths()["include"]) / "Python.h").exists():
        pytest.skip("Python headers missing")
    if not (shutil.which(os.environ.get("CC", "cc")) or shutil.which("gcc")):
        pytest.skip("no C compiler")
    tmp = tmp_path_factory.mktemp("pypm_pyx")
    for rel in ("Pypm.pyx", "PMLL.c", "PMLL.h"):
        shutil.copy(ROOT / rel, tmp / rel)
    proc = subprocess.run([sys.executable, "-m", "Cython.Build.Cythonize", "-i", "-3", "Pypm.pyx"],
                          cwd=tmp, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
    so = next(p for p in tmp.iterdir() if p.name.startswith("Pypm.") and p.suffix in (".so", ".pyd"))
    spec = importlib.util.spec_from_file_location("Pypm", so)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_silo_roundtrip(pypm):
    s = pypm.Silo(8)
    assert (s.size, s.slot_count) == (8, 0)
    assert s.peek("k") is None
    i = s.set("k", "value one")
    j = s.set(None, "value two")
    assert s.peek("k") == ("value one", i)
    assert s.peek(index=j) == ("value two", j)
    assert s.slot_count == 2 and s.slot(i) == ("k", "value one", True)
    s.set("k", "updated", index=i)
    assert s.peek("k") == ("updated", i) and s.slot_count == 2


def test_silo_full_and_bad_index(pypm):
    s = pypm.Silo(1)
    s.set("a", "x")
    with pytest.raises(ValueError):
        s.set("b", "y")
    with pytest.raises(ValueError):
        pypm.Silo(4).set("a", "x", index=9)
    with pytest.raises(IndexError):
        s.slot(5)


def test_semantic_peek_and_embeddings(pypm):
    s = pypm.Silo(4)
    s.set("a", "persistent memory logic loop")
    s.set("b", "gaussian elimination over gf two")
    hit = s.peek_semantic("persistent memory logic loop", 0.9)
    assert hit is not None and hit[0] == "persistent memory logic loop" and hit[2] > 0.99
    v = pypm.embed_text("hello world")
    assert len(v) == pypm.EMBED_DIM
    assert abs(sum(x * x for x in v) - 1.0) < 1e-4
    assert abs(pypm.cosine_similarity(v, v) - 1.0) < 1e-4
    with pytest.raises(ValueError):
        pypm.cosine_similarity([1.0], [1.0, 2.0])


def test_tree_update(pypm):
    s = pypm.Silo(4)
    s.update(3, 1)
    t = s.tree()
    assert len(t) == 8 and t[3] == 1
    s.update(99, 1)  # out of range: ignored by update_silo
    assert len(s.tree()) == 8


def _brute_sat(n, clauses):
    return any(pypm_check(clauses, list(bits)) for bits in itertools.product((0, 1), repeat=n))


def pypm_check(clauses, a):
    return all(any(a[abs(lit) - 1] == (1 if lit > 0 else 0) for lit in c) for c in clauses)


def test_check_assignment_matches_definition(pypm):
    rng = random.Random(7)
    for _ in range(200):
        n = rng.randint(1, 5)
        clauses = [[rng.choice((1, -1)) * rng.randint(1, n) for _ in range(rng.randint(1, 3))]
                   for _ in range(rng.randint(1, 6))]
        a = [rng.randint(0, 1) for _ in range(n)]
        assert pypm.check_assignment(clauses, a) == pypm_check(clauses, a)


def test_solve_sat_contract(pypm, tmp_path):
    # Unit clauses force the answer; the loop must find it.
    out = tmp_path / "a.pgm"
    sol = pypm.solve_sat(3, [[1], [-2], [3]], str(out))
    assert sol == [1, 0, 1]
    data = out.read_bytes()
    assert data.startswith(b"P5\n3 1\n255\n") and data[-3:] == bytes([255, 0, 255])
    # Random formulas: values are in {-1,0,1}; a full assignment reported for an
    # UNSAT formula can never pass check_assignment (no false positives).
    rng = random.Random(11)
    for _ in range(150):
        n = rng.randint(1, 6)
        clauses = [[rng.choice((1, -1)) * rng.randint(1, n) for _ in range(rng.randint(1, 3))]
                   for _ in range(rng.randint(1, 10))]
        sol = pypm.solve_sat(n, clauses)
        assert len(sol) == n and set(sol) <= {-1, 0, 1}
        if pypm.check_assignment(clauses, sol):
            assert _brute_sat(n, clauses)


def test_solve_sat_rejects_bad_literals(pypm):
    with pytest.raises(ValueError):
        pypm.solve_sat(2, [[3]])
    with pytest.raises(ValueError):
        pypm.solve_sat(2, [[0]])
