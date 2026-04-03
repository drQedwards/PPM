"""
tests/test_solution_engine.py — Tests for the Context+ solution engine.
"""

import sys
import os

import pytest

MCP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, MCP_DIR)

from pmll_memory_mcp.kv_store import get_store, _session_stores
from pmll_memory_mcp.memory_graph import upsert_node, _graph_stores
from pmll_memory_mcp.embeddings import reset_vectorizer
from pmll_memory_mcp.solution_engine import (
    resolve_context,
    promote_to_long_term,
    get_memory_status,
)


@pytest.fixture(autouse=True)
def reset_state():
    """Reset all module-level state before each test."""
    _session_stores.clear()
    _graph_stores.clear()
    reset_vectorizer()
    yield
    _session_stores.clear()
    _graph_stores.clear()
    reset_vectorizer()


# ---------------------------------------------------------------------------
# resolve_context
# ---------------------------------------------------------------------------


class TestResolveContext:
    def test_short_term_hit(self):
        store = get_store("s1")
        store.set("url", "https://example.com")
        result = resolve_context("s1", "url", store)
        assert result["source"] == "short_term"
        assert result["value"] == "https://example.com"
        assert result["score"] == 1.0

    def test_long_term_hit(self):
        store = get_store("s1")
        upsert_node("s1", "concept", "authentication", "user login system")
        result = resolve_context("s1", "authentication", store)
        assert result["source"] == "long_term"
        assert result["value"] is not None
        assert result["score"] > 0

    def test_miss(self):
        store = get_store("s1")
        result = resolve_context("s1", "nonexistent", store)
        assert result["source"] == "miss"
        assert result["value"] is None
        assert result["score"] == 0.0

    def test_short_term_priority(self):
        store = get_store("s1")
        store.set("auth", "cached-value")
        upsert_node("s1", "concept", "auth", "graph-value")
        result = resolve_context("s1", "auth", store)
        assert result["source"] == "short_term"
        assert result["value"] == "cached-value"


# ---------------------------------------------------------------------------
# promote_to_long_term
# ---------------------------------------------------------------------------


class TestPromoteToLongTerm:
    def test_creates_memory_node(self):
        result = promote_to_long_term("s1", "api-key", "secret", "note")
        assert result["promoted"] is True
        assert result["node_id"].startswith("mn-")

    def test_default_type_is_concept(self):
        result = promote_to_long_term("s1", "config", "app config")
        assert result["promoted"] is True


# ---------------------------------------------------------------------------
# get_memory_status
# ---------------------------------------------------------------------------


class TestGetMemoryStatus:
    def test_empty_session(self):
        store = get_store("s1")
        status = get_memory_status("s1", store)
        assert status["short_term"]["slots"] == 0
        assert status["short_term"]["silo_size"] == 256
        assert status["long_term"]["nodes"] == 0
        assert status["long_term"]["edges"] == 0
        assert status["promotion_threshold"] == 3

    def test_reflects_state(self):
        store = get_store("s1")
        store.set("k1", "v1")
        store.set("k2", "v2")
        upsert_node("s1", "concept", "c1", "content")
        status = get_memory_status("s1", store)
        assert status["short_term"]["slots"] == 2
        assert status["long_term"]["nodes"] == 1
