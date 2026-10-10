"""Build-memory scaling fixes: structured keys are exact-only in
resolve_context, directory-aware stale_paths, caller-chosen grouping,
batched commits and the memory_graph label/edge indexes."""
import importlib.util
import json
import random
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp"))

from pmll_memory_mcp import memory_graph as mg  # noqa: E402
from pmll_memory_mcp.kv_store import PMMemoryStore  # noqa: E402
from pmll_memory_mcp.solution_engine import (  # noqa: E402
    MIN_SEMANTIC_SCORE, is_structured_key, resolve_context,
)

_spec = importlib.util.spec_from_file_location("build_to_memory", ROOT / "tools" / "build_memory" / "build_to_memory.py")
btm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(btm)

ZERO_SRC = "src:" + "0" * 64
NEAR_PATH = "path:go-ethereum/core/does-not-exist"


@pytest.fixture()
def db(tmp_path):
    path = str(tmp_path / "g.sqlite3")
    mg.configure_db(path)
    yield path
    mg.configure_db(str(tmp_path / "after.sqlite3"))


def _geth_like(session):
    """Nodes shaped like the go-ethereum build graph (same label/content format)."""
    pkgs = {"core/vm": "3c3d758ba5c249f3", "core/vm/program": "6c71d1fdbb4a78c9",
            "crypto/keccak": "a1b2c3d4e5f60718", "core/types": "0f1e2d3c4b5a6978",
            "eth/tracers/native": "1122334455667788"}
    for p, sha16 in pkgs.items():
        sha = sha16 * 4
        mg.upsert_node(session, "file", f"path:go-ethereum/{p}",
                       f"go-ethereum/{p}: content sha256 {sha16} built with status ok",
                       {"sha256": sha, "path": p})
        mg.upsert_node(session, "file", f"src:{sha}",
                       f"{Path(p).name} [go] OK; warnings=0. Path go-ethereum/{p}.", {"sha256": sha})
    mg.upsert_node(session, "concept", "module:go:core", "go:core: kinds=go; units=3; failing=none")
    return pkgs


# -- resolve_context: structured keys --------------------------------------------------

@pytest.mark.parametrize("key", [NEAR_PATH, ZERO_SRC])
def test_structured_near_miss_is_a_miss(db, key):
    _geth_like("s")
    r = resolve_context("s", key, PMMemoryStore())
    assert r == {"source": "miss", "value": None, "score": 0.0, "match": None, "node_id": None}


@pytest.mark.parametrize("key", [NEAR_PATH, ZERO_SRC])
def test_semantic_fallback_would_have_matched(db, key):
    """The regression: with the semantic step forced on, these never-stored keys
    clear MIN_SEMANTIC_SCORE and come back as some other package."""
    _geth_like("s")
    r = resolve_context("s", key, PMMemoryStore(), exact_only=False)
    assert r["match"] == "semantic" and r["score"] >= MIN_SEMANTIC_SCORE


def test_structured_exact_hits_still_work(db):
    pkgs = _geth_like("s")
    store = PMMemoryStore()
    for key in ("path:go-ethereum/core/vm", f"src:{pkgs['core/vm'] * 4}", "module:go:core"):
        r = resolve_context("s", key, store)
        assert r["source"] == "long_term" and r["match"] == "exact" and r["score"] == 1.0


def test_free_text_keeps_semantic_fallback(db):
    mg.upsert_node("s", "concept", "database pooling", "PostgreSQL connection pooling configuration")
    r = resolve_context("s", "PostgreSQL connection pooling configuration", PMMemoryStore())
    assert r["match"] == "semantic"


def test_exact_only_true_applies_to_free_text(db):
    mg.upsert_node("s", "concept", "database pooling", "PostgreSQL connection pooling configuration")
    r = resolve_context("s", "PostgreSQL connection pooling configuration", PMMemoryStore(), exact_only=True)
    assert r["source"] == "miss"


@pytest.mark.parametrize("key,expected", [
    ("path:a/b", True), ("src:00", True), ("module:x", True), ("build:abc", True),
    ("path:", False), ("path: spaced", False), ("auth", False), ("xpath:a", False), ("Path:a", False),
])
def test_is_structured_key(key, expected):
    assert is_structured_key(key) is expected


# -- memory_graph indexes ----------------------------------------------------------------

def test_upsert_by_type_and_label_uses_index_not_duplicates(db):
    a = mg.upsert_node("s", "file", "path:x", "one")
    b = mg.upsert_node("s", "file", "path:x", "two")
    c = mg.upsert_node("s", "note", "path:x", "other type")
    assert a.id == b.id != c.id and b.content == "two"
    assert mg.get_graph_stats("s")["nodes"] == 2
    assert {n.id for n in mg._get_graph("s").nodes_by_label("path:x")} == {a.id, c.id}


def test_relation_upsert_and_adjacency_match_linear_scan(db):
    rnd = random.Random(7)
    ids = [mg.upsert_node("s", "concept", f"n{i}", f"node {i}").id for i in range(40)]
    for _ in range(200):
        mg.create_relation("s", rnd.choice(ids), rnd.choice(ids), rnd.choice(["depends_on", "contains"]))
    g = mg._get_graph("s")
    keys = [(e.source, e.target, e.relation) for e in g.edges.values()]
    assert len(keys) == len(set(keys))  # upsert, never duplicate
    for nid in ids:
        linear = [e for e in g.edges.values() if e.source == nid or e.target == nid]
        assert mg._get_edges_for_node(g, nid) == linear  # same edges, same order


def test_index_survives_reload_prune_and_import(db):
    a = mg.upsert_node("s", "file", "a", "A")
    b = mg.upsert_node("s", "file", "b", "B")
    mg.create_relation("s", a.id, b.id, "depends_on", weight=0.01)
    assert mg.reload_session_from_db("s") == {"nodes": 2, "edges": 1}
    assert mg.find_node_by_label("s", "a").id == a.id
    mg.prune_stale_links("s")  # weight 0.01 < STALE_THRESHOLD: edge goes
    g = mg._get_graph("s")
    assert g.edges_for_node(a.id) == [] and g.edge_by_key(a.id, b.id, "depends_on") is None
    mg.import_graph("t", mg.export_graph("s"))
    assert mg.find_node_by_label("t", "b").id == b.id


def test_index_resyncs_after_direct_dict_edits(db):
    a = mg.upsert_node("s", "file", "a", "A")
    g = mg._get_graph("s")
    del g.nodes[a.id]  # outside the module's helpers
    assert mg.find_node_by_label("s", "a") is None
    again = mg.upsert_node("s", "file", "a", "A2")
    assert again.id != a.id and mg.find_node_by_label("s", "a").id == again.id


# -- batched commits -----------------------------------------------------------------------

def _rows(path):
    with sqlite3.connect(path) as c:
        return c.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]


def test_batch_defers_commit_until_exit(db):
    with mg.batch():
        for i in range(5):
            mg.upsert_node("s", "concept", f"k{i}", "v")
        assert _rows(db) == 0  # other connections see nothing yet
    assert _rows(db) == 5


def test_batch_rolls_back_and_drops_cache_on_error(db):
    mg.upsert_node("s", "concept", "kept", "v")
    with pytest.raises(RuntimeError):
        with mg.batch():
            mg.upsert_node("s", "concept", "lost", "v")
            raise RuntimeError("boom")
    assert _rows(db) == 1
    assert mg.find_node_by_label("s", "lost") is None and mg.find_node_by_label("s", "kept")


def test_load_sqlite_commits_once(db, monkeypatch, tmp_path):
    nodes = {f"n{i}": {"type": "concept", "label": f"n{i}", "content": "c", "metadata": {}} for i in range(30)}
    edges = [(f"n{i}", f"n{i + 1}", "depends_on") for i in range(29)]
    calls = {"n": 0}
    real = mg._conn

    class Spy:
        def __init__(self, c):
            self._c = c

        def commit(self):
            calls["n"] += 1
            return self._c.commit()

        def __getattr__(self, name):
            return getattr(self._c, name)

    target = str(tmp_path / "once.sqlite3")
    info = btm.load_sqlite(target, "s", nodes, edges, str(ROOT))  # str root accepted
    assert info["nodes"] == 30 and info["edges_created"] == 29
    monkeypatch.setattr(mg, "_conn", lambda: Spy(real()))
    btm.load_sqlite(target, "s", nodes, edges, ROOT)
    assert calls["n"] == 1


# -- grouping and directory-aware staleness ------------------------------------------------

@pytest.fixture()
def pkg_repo(tmp_path):
    root = tmp_path / "gorepo"
    for d in ("core/vm", "core/types", "p2p", "cmd/abigen", "accounts/abi/abigen"):
        (root / d).mkdir(parents=True)
        (root / d / "x.go").write_text(f"package {Path(d).name}\n")
    units = []
    for d in ("core/vm", "core/types", "p2p", "cmd/abigen", "accounts/abi/abigen"):
        files = [f"{d}/x.go"]
        units.append({"path": d, "sha256": btm.files_sha256(root, files), "files": files, "kind": "go",
                      "ok": True, "warnings": 0, "first_errors": [],
                      "depends_on_units": ["core/types"] if d == "core/vm" else []})
    return root, {"units": units, "meta": {"repo": "gorepo"}}


def test_default_grouping_collides_on_basename(pkg_repo):
    root, results = pkg_repo
    _, nodes, edges, _ = btm.build(results, root)
    members = [t for s, t, r in edges if s == "module:abigen"]
    assert len(members) == 2  # cmd/abigen and accounts/abi/abigen share a stem


def test_caller_grouping(pkg_repo):
    root, results = pkg_repo
    _, nodes, edges, _ = btm.build(results, root, group=btm.module_by_toplevel)
    assert {s for s, _, r in edges if r == "contains"} == {"module:core", "module:p2p", "module:cmd", "module:accounts"}
    _, _, edges, _ = btm.build(results, root, group=lambda p: "all")
    assert {s for s, _, r in edges if r == "contains"} == {"module:all"}
    _, _, edges, _ = btm.build(results, root, group=btm.module_by_dir)
    assert ("module:cmd/abigen", "path:gorepo/cmd/abigen", "contains") in edges


def test_unit_declared_dependencies(pkg_repo):
    root, results = pkg_repo
    _, _, edges, _ = btm.build(results, root)
    vm, types = (next(u["sha256"] for u in results["units"] if u["path"] == p) for p in ("core/vm", "core/types"))
    assert (f"src:{vm}", f"src:{types}", "depends_on") in edges


def test_directory_stale_paths(pkg_repo, db):
    root, results = pkg_repo
    _, nodes, edges, _ = btm.build(results, root, group=btm.module_by_toplevel)
    btm.load_sqlite(db, "s", nodes, edges, ROOT)
    assert btm.stale_paths(db, "s", root) == []  # no edits: nothing stale
    (root / "core" / "vm" / "x.go").write_text("package vm\n// edit\n")
    rows = btm.stale_paths(db, "s", root)
    assert [r["path"] for r in rows] == ["core/vm"] and rows[0]["current_content_built"] == "False"


def test_directory_without_files_list_hashes_directory(tmp_path, db):
    root = tmp_path / "r"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "a.c").write_text("int a;\n")
    sha = btm.files_sha256(root, btm.dir_files(root, "pkg"))
    results = {"units": [{"path": "pkg", "sha256": sha, "kind": "c", "ok": True}], "meta": {"repo": "r"}}
    _, nodes, edges, _ = btm.build(results, root)
    btm.load_sqlite(db, "s", nodes, edges, ROOT)
    assert btm.stale_paths(db, "s", root) == []
    (root / "pkg" / "b.c").write_text("int b;\n")  # new file in the directory
    assert [r["path"] for r in btm.stale_paths(db, "s", root)] == ["pkg"]


def test_cli_group_and_root(pkg_repo, tmp_path):
    root, results = pkg_repo
    src = tmp_path / "res.json"
    src.write_text(json.dumps(results))
    out = tmp_path / "nodes.json"
    assert btm.main([str(src), "--out", str(out), "--root", str(root), "--group", "toplevel"]) == 0
    labels = {n["label"] for n in json.loads(out.read_text())["nodes"]}
    assert "module:core" in labels and "module:abigen" not in labels
