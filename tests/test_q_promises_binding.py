"""Q_promise_lib Python bindings: the ctypes module (Q_promises.py, against the
built libqpromise.so) and the Cython module (Q_promises.pyx, compiled in a temp
dir against qpromise.c + PMLL.c). Both expose the same API and run the same tests.
The Cython variant is skipped when Cython / headers / a C compiler are missing."""
import importlib.util
import os
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
QLIB = ROOT / "Q_promise_lib"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ctypes_mod():
    if not (QLIB / "libqpromise.so").exists():
        subprocess.check_call(["make", "shared"], cwd=QLIB)
    return _load("Q_promises_ctypes", QLIB / "Q_promises.py")


def _cython_mod(tmp):
    for m in ("Cython", "setuptools"):
        if importlib.util.find_spec(m) is None:
            pytest.skip(f"{m} not installed")
    if not (Path(sysconfig.get_paths()["include"]) / "Python.h").exists():
        pytest.skip("Python headers missing")
    if not (shutil.which(os.environ.get("CC", "cc")) or shutil.which("gcc")):
        pytest.skip("no C compiler")
    for rel in ("Q_promise_lib/Q_promises.pyx", "Q_promise_lib/qpromise.c", "Q_promise_lib/qpromise.h",
                "PMLL.c", "PMLL.h"):
        dst = tmp / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, dst)
    (tmp / "setup_q.py").write_text(
        "from setuptools import setup, Extension\n"
        "from Cython.Build import cythonize\n"
        "ext = Extension('Q_promises', ['Q_promise_lib/Q_promises.pyx', 'Q_promise_lib/qpromise.c', 'PMLL.c'],\n"
        "                include_dirs=['Q_promise_lib', '.'], define_macros=[('PMLL_NO_MAIN', '1')])\n"
        "setup(ext_modules=cythonize([ext], language_level=3, quiet=True))\n")
    proc = subprocess.run([sys.executable, "setup_q.py", "build_ext", "--inplace"], cwd=tmp,
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
    so = next(p for p in tmp.iterdir() if p.name.startswith("Q_promises.") and p.suffix in (".so", ".pyd"))
    return _load("Q_promises", so)


@pytest.fixture(scope="module", params=["ctypes", "cython"])
def qp(request, tmp_path_factory):
    if request.param == "ctypes":
        return _ctypes_mod()
    return _cython_mod(tmp_path_factory.mktemp("qp_cython"))


def test_silo_set_peek_and_semantic(qp):
    silo = qp.Silo(8)
    assert silo.peek("missing") is None
    idx = silo.set("build:abc", '{"status":"ok"}')
    assert silo.peek("build:abc") == ('{"status":"ok"}', idx)
    assert silo.peek(index=idx)[0] == '{"status":"ok"}'
    hit = silo.peek_semantic('{"status":"ok"}', 0.9)
    assert hit is not None and hit[1] == idx and hit[2] > 0.99


def test_silo_full_raises(qp):
    silo = qp.Silo(2)
    silo.set("a", "1")
    silo.set("b", "2")
    with pytest.raises(qp.QPromiseError):
        silo.set("c", "3")


def test_from_peek_miss_then_resolve_commit_then_hit(qp):
    silo = qp.Silo(8)
    p = qp.Promise.from_peek(silo, "build:sha")
    assert p.state == qp.PENDING and p.pmll_key == "build:sha"
    seen = []
    child = p.then(lambda v: seen.append(v) or v.upper())
    assert p.resolve_commit("ok") is True
    assert seen == []                 # continuations wait for drain()
    qp.drain()
    assert seen == ["ok"] and child.state == qp.RESOLVED and child.value == "OK"
    assert silo.peek("build:sha")[0] == "ok"
    again = qp.Promise.from_peek(silo, "build:sha")
    assert again.state == qp.RESOLVED and again.value == "ok"


def test_no_double_settle(qp):
    p = qp.Promise.create()
    assert p.resolve("x") is True
    assert p.resolve("y") is False and p.reject("z") is False and p.cancel() is False
    assert p.value == "x"


def test_catch_and_handler_exception_rejects(qp):
    r = qp.Promise.rejected("boom").catch(lambda e: "recovered:" + e)
    bad = qp.Promise.resolved("v").then(lambda v: 1 / 0)
    qp.drain()
    assert r.state == qp.RESOLVED and r.value == "recovered:boom"
    assert bad.state == qp.REJECTED and "division" in bad.error


def test_then_passes_rejection_through(qp):
    child = qp.Promise.rejected("nope").then(lambda v: "unused")
    qp.drain()
    assert child.state == qp.REJECTED and child.error == "nope"


def test_adopt_returned_promise_and_finally(qp):
    order = []
    a = qp.Promise.resolved("a").then(lambda v: qp.Promise.resolved(v + "b"))
    f = a.finally_(lambda: order.append("finally"))
    qp.drain()
    assert a.state == qp.RESOLVED and a.value == "ab"
    assert order == ["finally"] and f.value == "ab"


def test_cancel_skips_then_runs_finally(qp):
    p = qp.Promise.create()
    ran = []
    t = p.then(lambda v: ran.append("then"))
    fin = p.finally_(lambda: ran.append("finally"))
    assert p.cancel() is True
    qp.drain()
    assert p.state == qp.CANCELLED and ran == ["finally"]
    assert t.state == qp.CANCELLED and fin.state == qp.CANCELLED
    assert qp.jobs_pending() == 0


def test_bind_pmll_metadata(qp):
    silo = qp.Silo(4)
    p = qp.Promise.create()
    assert p.bind_pmll(silo, "k", 7, "ctx") is True
    assert (p.pmll_key, p.pmll_sat_id, p.pmll_context) == ("k", 7, "ctx")
    assert p.resolve_commit("v") is True
    assert silo.peek("k")[0] == "v"


def test_semantic_from_peek(qp):
    silo = qp.Silo(4)
    silo.set("doc", "persistent memory logic loop")
    hit = qp.Promise.from_peek_semantic(silo, "persistent memory logic loop", 0.9)
    miss = qp.Promise.from_peek_semantic(silo, "zzz qqq", 0.9)
    assert hit.state == qp.RESOLVED and hit.value == "persistent memory logic loop"
    assert miss.state == qp.PENDING and miss.pmll_context == "zzz qqq"
