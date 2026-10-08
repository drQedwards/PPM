"""resolve_context: exact label lookup and minimum semantic score (Python MCP)."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp"))

from pmll_memory_mcp import memory_graph as mg  # noqa: E402
from pmll_memory_mcp.kv_store import PMMemoryStore  # noqa: E402
from pmll_memory_mcp.solution_engine import MIN_SEMANTIC_SCORE, resolve_context  # noqa: E402

SHA_A = "build:b70a337709832f585bc8ad4464182e34ef3cd9bf5d96826b34bede83379248bc"
SHA_NEVER = "build:5f0c2a9e7d4b1c3a8e6f2d0b9a7c5e3f1d8b6a4c2e0f9d7b5a3c1e8f6d4b2a0c"


@pytest.fixture()
def graph(tmp_path):
    mg.configure_db(str(tmp_path / "g.sqlite3"))
    s = "s-thresh"
    mg.upsert_node(s, "file", SHA_A, '{"status":"ok","w":0}')
    mg.upsert_node(s, "note", "build:6d31470f6c8b", "Batch build: 28/58 units OK; 10 CUDA units skipped.")
    mg.upsert_node(s, "concept", "module:Panda", "Panda: kinds=c,pyx; failing=Panda.c")
    yield s
    mg.configure_db(str(tmp_path / "after.sqlite3"))


def test_never_stored_key_is_a_miss(graph):
    r = resolve_context(graph, SHA_NEVER, PMMemoryStore())
    assert r == {"source": "miss", "value": None, "score": 0.0, "match": None, "node_id": None}


def test_exact_label_hit(graph):
    r = resolve_context(graph, SHA_A, PMMemoryStore())
    assert r["source"] == "long_term" and r["match"] == "exact" and r["score"] == 1.0
    assert r["value"] == '{"status":"ok","w":0}' and r["node_id"].startswith("mn-")


def test_short_term_wins(graph):
    store = PMMemoryStore()
    store.set(SHA_A, "cached")
    r = resolve_context(graph, SHA_A, store)
    assert r["source"] == "short_term" and r["value"] == "cached" and r["match"] == "exact"


def test_exact_label_beats_semantically_closer_node(tmp_path):
    mg.configure_db(str(tmp_path / "g2.sqlite3"))
    mg.upsert_node("s2", "concept", "auth", "graph-value")
    mg.upsert_node("s2", "concept", "auth login", "auth auth auth login")
    r = resolve_context("s2", "auth", PMMemoryStore())
    assert r["match"] == "exact" and r["value"] == "graph-value"


def test_semantic_hit_above_threshold(tmp_path):
    mg.configure_db(str(tmp_path / "g3.sqlite3"))
    mg.upsert_node("s3", "concept", "database pooling", "PostgreSQL connection pooling configuration")
    r = resolve_context("s3", "PostgreSQL connection pooling configuration", PMMemoryStore())
    assert r["source"] == "long_term" and r["match"] == "semantic" and r["score"] >= MIN_SEMANTIC_SCORE


def test_min_score_parameter(graph):
    store = PMMemoryStore()
    assert resolve_context(graph, SHA_NEVER, store, min_score=0.0)["match"] == "semantic"
    assert resolve_context(graph, SHA_NEVER, store, min_score=1.0)["source"] == "miss"


def test_empty_graph_is_a_miss_at_any_threshold(tmp_path):
    mg.configure_db(str(tmp_path / "g4.sqlite3"))
    assert resolve_context("empty", "anything", PMMemoryStore(), min_score=0.0)["source"] == "miss"
