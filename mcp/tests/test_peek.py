"""
tests/test_peek.py — Tests for peek_context() (peek.py).

Validates hit/miss/pending return values from the deduplication guard.
"""

import sys
import os

import pytest

MCP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, MCP_DIR)

from pmll_memory_mcp.kv_store import PMMemoryStore
from pmll_memory_mcp.q_promise_bridge import QPromiseRegistry
from pmll_memory_mcp.peek import peek_context


@pytest.fixture()
def store():
    return PMMemoryStore()


@pytest.fixture()
def registry():
    return QPromiseRegistry()


# ---------------------------------------------------------------------------
# peek_context tests
# ---------------------------------------------------------------------------

class TestPeekContextKVHit:
    def test_returns_hit_when_key_cached(self, store, registry):
        store.set("my-key", "my-value")
        result = peek_context("my-key", "session-1", store, registry)
        assert result["hit"] is True
        assert result["value"] == "my-value"
        assert result["index"] == 0

    def test_hit_does_not_modify_store(self, store, registry):
        store.set("k", "v")
        before_len = len(store)
        peek_context("k", "session-1", store, registry)
        assert len(store) == before_len


class TestPeekContextQPromisePending:
    def test_returns_pending_when_promise_in_flight(self, store, registry):
        registry.register("pending-key")
        result = peek_context("pending-key", "session-1", store, registry)
        assert result["hit"] is True
        assert result["status"] == "pending"
        assert result["promise_id"] == "pending-key"

    def test_resolved_promise_not_returned_as_pending(self, store, registry):
        registry.register("done-key")
        registry.resolve("done-key", "payload-data")
        # KV store has no entry, promise is resolved (not pending)
        result = peek_context("done-key", "session-1", store, registry)
        assert result["hit"] is False

    def test_kv_hit_takes_priority_over_promise(self, store, registry):
        store.set("key", "cached-value")
        registry.register("key")  # also a pending promise
        result = peek_context("key", "session-1", store, registry)
        assert result["hit"] is True
        assert result["value"] == "cached-value"  # KV wins


class TestPeekContextFullMiss:
    def test_returns_miss_when_key_unknown(self, store, registry):
        result = peek_context("totally-new-key", "session-1", store, registry)
        assert result == {"hit": False}

    def test_miss_does_not_add_to_store(self, store, registry):
        peek_context("new-key", "session-1", store, registry)
        hit, _, _ = store.peek("new-key")
        assert hit is False
