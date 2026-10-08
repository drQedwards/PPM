"""tools/build_memory: results -> nodes/edges/silo keys, SQLite round trip,
exact read-back through resolve_context, and staleness detection."""
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp"))

from pmll_memory_mcp import memory_graph as mg  # noqa: E402
from pmll_memory_mcp.kv_store import PMMemoryStore  # noqa: E402
from pmll_memory_mcp.solution_engine import resolve_context  # noqa: E402

_spec = importlib.util.spec_from_file_location("build_to_memory", ROOT / "tools" / "build_memory" / "build_to_memory.py")
btm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(btm)


def _sha(p):
    import hashlib
    return hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.fixture()
def mini_repo(tmp_path):
    root = tmp_path / "repo"
    (root / "lib").mkdir(parents=True)
    (root / "lib" / "a.h").write_text("int a(void);\n")
    (root / "lib" / "a.c").write_text('#include "a.h"\nint a(void) { return 1; }\n')
    (root / "b.c").write_text("int b(void) { return undefined_name; }\n")
    (root / "c.pyx").write_text("def c():\n    return 1\n")
    units = [
        {"path": "lib/a.c", "sha256": _sha(root / "lib" / "a.c"), "kind": "c", "required": True,
         "ok": True, "warnings": 0, "first_errors": []},
        {"path": "b.c", "sha256": _sha(root / "b.c"), "kind": "c", "required": False, "ok": False,
         "warnings": 0, "first_errors": ["b.c:1:28: error: 'undefined_name' undeclared"]},
        {"path": "c.pyx", "sha256": _sha(root / "c.pyx"), "kind": "pyx", "required": True, "ok": True,
         "warnings": 0, "first_errors": []},
        {"path": "k.cu", "sha256": "0" * 64, "kind": "cuda", "required": False, "ok": None,
         "warnings": 0, "first_errors": ["skipped: nvcc not available"]},
    ]
    results = {"units": units, "required_failures": 0,
               "meta": {"repo": "mini", "head": "abc123", "generated_at": "2026-10-08T15:00:00-0400"}}
    return root, results


@pytest.fixture()
def tmp_db(tmp_path):
    db = str(tmp_path / "graph.sqlite3")
    yield db
    mg.configure_db(str(tmp_path / "after.sqlite3"))


def test_nodes_edges_and_silo_keys(mini_repo):
    root, results = mini_repo
    run_id, nodes, edges, kv = btm.build(results, root)
    a_sha = results["units"][0]["sha256"]
    assert nodes[f"src:{a_sha}"]["metadata"]["status"] == "ok"
    b = nodes[f"src:{results['units'][1]['sha256']}"]
    assert b["metadata"]["status"] == "fail" and "undefined_name" in b["metadata"]["first_error"]
    assert nodes["src:" + "0" * 64]["metadata"]["status"] == "skipped"
    assert nodes["path:mini/lib/a.c"]["metadata"]["sha256"] == a_sha
    assert nodes[f"build:{run_id}"]["type"] == "note"
    assert ("module:a", "path:mini/lib/a.c", "contains") in edges
    assert ("path:mini/lib/a.c", f"src:{a_sha}", "references") in edges
    h_sha = _sha(root / "lib" / "a.h")
    assert (f"src:{a_sha}", f"src:{h_sha}", "depends_on") in edges
    assert json.loads(kv[f"build:{a_sha}"])["status"] == "ok"
    assert all(isinstance(v, str) for n in nodes.values() for v in n["metadata"].values())
    assert all(s in nodes and t in nodes for s, t, _ in edges)


def test_sqlite_roundtrip_and_exact_readback(mini_repo, tmp_db):
    root, results = mini_repo
    run_id, nodes, edges, kv = btm.build(results, root)
    info = btm.load_sqlite(tmp_db, "s-build", nodes, edges, root)
    assert info["nodes"] == len(nodes) and info["edges_created"] == len(edges)
    assert mg.reload_session_from_db("s-build") == {"nodes": len(nodes), "edges": len(edges)}
    store = PMMemoryStore()
    b_sha = results["units"][1]["sha256"]
    hit = resolve_context("s-build", f"src:{b_sha}", store)
    assert hit["source"] == "long_term" and hit["match"] == "exact" and "FAIL" in hit["value"]
    never = resolve_context("s-build", "src:" + "f" * 64, store)
    assert never["source"] == "miss" and never["value"] is None


def test_stale_detection(mini_repo, tmp_db):
    root, results = mini_repo
    _, nodes, edges, _ = btm.build(results, root)
    btm.load_sqlite(tmp_db, "s-stale", nodes, edges, root)
    assert btm.stale_paths(tmp_db, "s-stale", root) == [
        {"path": "k.cu", "built_sha256": "0" * 64, "current_sha256": "missing", "current_content_built": "False"}]
    with open(root / "lib" / "a.c", "a") as fh:
        fh.write("/* edit */\n")
    rows = {r["path"]: r for r in btm.stale_paths(tmp_db, "s-stale", root)}
    assert rows["lib/a.c"]["current_sha256"] == _sha(root / "lib" / "a.c")
    assert rows["lib/a.c"]["current_content_built"] == "False"


def test_real_repo_unit_list_maps(tmp_path):
    """The CI unit schema feeds straight in (no compile: synthesize from tracked files)."""
    bbc_spec = importlib.util.spec_from_file_location("bbc", ROOT / "tools" / "ci" / "batch_build_check.py")
    bbc = importlib.util.module_from_spec(bbc_spec)
    bbc_spec.loader.exec_module(bbc)
    units = [{"path": p, "sha256": _sha(ROOT / p), "kind": "c", "required": p in bbc.REQUIRED_C,
              "ok": True, "warnings": 0, "first_errors": []} for p in bbc.REQUIRED_C if (ROOT / p).is_file()]
    _, nodes, edges, kv = btm.build({"units": units, "meta": {"repo": "repo"}}, ROOT)
    assert len(kv) == len({u["sha256"] for u in units})
    assert "module:Q_promise" in nodes and "module:PMLL" in nodes
    if shutil.which("git"):
        assert any(r == "depends_on" for _, _, r in edges)
