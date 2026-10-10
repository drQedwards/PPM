"""tools/build_memory/go_batch_build.py on a tiny fixture Go module (no
go-ethereum clone needed). Skipped when `go` is not on PATH."""
import importlib.util
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp"))

from pmll_memory_mcp import memory_graph as mg  # noqa: E402
from pmll_memory_mcp.kv_store import PMMemoryStore  # noqa: E402
from pmll_memory_mcp.solution_engine import resolve_context  # noqa: E402

_spec = importlib.util.spec_from_file_location("go_batch_build", ROOT / "tools" / "build_memory" / "go_batch_build.py")
gbb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gbb)
btm = gbb.btm

needs_go = pytest.mark.skipif(shutil.which("go") is None, reason="go toolchain not installed")
needs_cgo = pytest.mark.skipif(shutil.which("go") is None or shutil.which("gcc") is None,
                               reason="go and gcc needed for the cgo package")

FILES = {
    "go.mod": "module example.com/fixture\n\ngo 1.20\n",
    "core/types/types.go": "package types\n\ntype Block struct{ N int }\n",
    "core/vm/vm.go": ('package vm\n\nimport "example.com/fixture/core/types"\n\n'
                      "func Run(b types.Block) int { return b.N + 1 }\n"),
    "core/vm/vm_test.go": ('package vm\n\nimport "testing"\n\n'
                           "func TestRun(t *testing.T) { _ = Run }\n"),
    "crypto/sec/sec.go": ('package sec\n\n// #include "inc/sec.h"\nimport "C"\n\n'
                          "func Add(a, b int) int { return int(C.sec_add(C.int(a), C.int(b))) }\n"),
    "crypto/sec/inc/sec.h": '#include "impl.h"\n',
    "crypto/sec/inc/impl.h": "static int sec_add(int a, int b) { return a + b; }\n",
    "tests/fuzz/fuzz_test.go": 'package fuzz\n\nimport "testing"\n\nfunc TestNothing(t *testing.T) {}\n',
    "cmd/tool/main.go": ('package main\n\nimport (\n\t"fmt"\n\t"example.com/fixture/core/vm"\n'
                         '\t"example.com/fixture/core/types"\n)\n\n'
                         'func main() { fmt.Println(vm.Run(types.Block{N: 1})) }\n'),
    "broken/broken.go": "package broken\n\nfunc F() int { return undefinedName }\n",
    "vetbad/vetbad.go": 'package vetbad\n\nimport "fmt"\n\nfunc F() string { return fmt.Sprintf("%d", "x") }\n',
}


@pytest.fixture()
def gomod(tmp_path, monkeypatch):
    root = tmp_path / "fixture"
    for rel, text in FILES.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    monkeypatch.setenv("GOFLAGS", "-mod=mod")
    monkeypatch.setenv("GOWORK", "off")
    monkeypatch.setenv("GOTOOLCHAIN", "local")
    return root


@pytest.fixture()
def db(tmp_path):
    path = str(tmp_path / "g.sqlite3")
    yield path
    mg.configure_db(str(tmp_path / "after.sqlite3"))


def _units(res):
    return {u["path"]: u for u in res["units"]}


@needs_cgo
def test_units_hashes_and_dependencies(gomod):
    units = {u["path"]: u for u in gbb.package_units(gomod)}
    assert set(units) == {"core/types", "core/vm", "crypto/sec", "tests/fuzz", "cmd/tool", "broken", "vetbad"}
    vm = units["core/vm"]
    assert vm["files"] == ["core/vm/vm.go", "core/vm/vm_test.go"]
    assert vm["sha256"] == btm.files_sha256(gomod, vm["files"])
    assert vm["depends_on_units"] == ["core/types"] and vm["kind"] == "go"
    assert units["cmd/tool"]["depends_on_units"] == ["core/types", "core/vm"]
    sec = units["crypto/sec"]
    assert sec["kind"] == "cgo"
    assert sec["includes"] == ["crypto/sec/inc/impl.h", "crypto/sec/inc/sec.h"]  # recursive closure
    assert set(sec["includes"]) <= set(sec["files"])


@needs_cgo
def test_build_vet_and_classification(gomod):
    res = gbb.run(gomod, jobs=2)
    u = _units(res)
    assert u["core/vm"]["ok"] and u["cmd/tool"]["ok"] and u["crypto/sec"]["ok"]
    assert u["tests/fuzz"]["test_only"] and u["tests/fuzz"]["ok"]
    assert not u["broken"]["build_ok"] and any("undefinedName" in e for e in u["broken"]["first_errors"])
    assert u["vetbad"]["build_ok"] and u["vetbad"]["vet_ok"] is False and not u["vetbad"]["ok"]
    assert u["vetbad"]["warnings"] >= 1
    assert not (gomod / "tool").exists() and not (gomod / "cmd" / "tool" / "tool").exists()  # -o /dev/null
    assert res["meta"]["module"] == "example.com/fixture"


@needs_go
def test_no_vet_option(gomod):
    shutil.rmtree(gomod / "crypto")  # no cgo needed for this test
    res = gbb.run(gomod, jobs=2, vet=False)
    u = _units(res)
    assert u["vetbad"]["ok"] and u["vetbad"]["vet_ok"] is None


@needs_cgo
def test_memory_graph_roundtrip_and_staleness(gomod, db):
    res = gbb.run(gomod, jobs=2, vet=False)
    run_id, nodes, edges, kv = btm.build(res, gomod, "fixture", btm.module_by_toplevel)
    u = _units(res)
    vm, types, sec = (u[p]["sha256"] for p in ("core/vm", "core/types", "crypto/sec"))
    assert (f"src:{vm}", f"src:{types}", "depends_on") in edges
    assert ("module:core", "path:fixture/core/vm", "contains") in edges
    assert sum(1 for s, _, r in edges if s == f"src:{sec}" and r == "depends_on") == 2  # two headers
    info = btm.load_sqlite(db, "go", nodes, edges, ROOT)
    assert info["nodes"] == len(nodes) and info["edges_created"] == len(edges)

    store = PMMemoryStore()
    assert resolve_context("go", "path:fixture/core/vm", store)["match"] == "exact"
    assert resolve_context("go", "path:fixture/core/does-not-exist", store)["source"] == "miss"
    assert resolve_context("go", "src:" + "0" * 64, store)["source"] == "miss"

    assert btm.stale_paths(db, "go", gomod) == []
    hasher = gbb.go_package_hasher(gomod)
    assert btm.stale_paths(db, "go", gomod, hasher=hasher) == []

    (gomod / "crypto/sec/inc/impl.h").write_text("static int sec_add(int a, int b) { return b + a; }\n")
    assert [r["path"] for r in btm.stale_paths(db, "go", gomod)] == ["crypto/sec"]  # header edit
    (gomod / "core/vm/extra.go").write_text("package vm\n\nfunc Extra() {}\n")
    assert [r["path"] for r in btm.stale_paths(db, "go", gomod)] == ["crypto/sec"]  # files list can't see it
    rows = btm.stale_paths(db, "go", gomod, hasher=gbb.go_package_hasher(gomod))
    assert [r["path"] for r in rows] == ["core/vm", "crypto/sec"]  # re-listing does


def test_skips_cleanly_without_go(monkeypatch, capsys):
    monkeypatch.setattr(gbb.shutil, "which", lambda name: None)
    assert gbb.go_available() is False
    assert gbb.main(["."]) == 2
    assert "go not found" in capsys.readouterr().err
