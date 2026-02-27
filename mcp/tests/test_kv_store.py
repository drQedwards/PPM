"""
tests/test_kv_store.py — Tests for PMMemoryStore (kv_store.py).

Validates peek hits/misses, set, flush, and session isolation via the
module-level get_store / drop_store helpers.
"""

import sys
import os

import pytest

# Ensure the mcp/ package is importable from the tests directory.
MCP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, MCP_DIR)

from pmll_memory_mcp.kv_store import PMMemoryStore, get_store, drop_store, _session_stores


@pytest.fixture(autouse=True)
def clean_stores():
    """Wipe the module-level store registry before each test."""
    _session_stores.clear()
    yield
    _session_stores.clear()


# ---------------------------------------------------------------------------
# PMMemoryStore unit tests
# ---------------------------------------------------------------------------

class TestPMMemoryStorePeek:
    def test_peek_miss_on_empty_store(self):
        store = PMMemoryStore()
        hit, value, index = store.peek("missing_key")
        assert hit is False
        assert value is None
        assert index is None

    def test_peek_hit_after_set(self):
        store = PMMemoryStore()
        store.set("url", "https://example.com")
        hit, value, index = store.peek("url")
        assert hit is True
        assert value == "https://example.com"
        assert index == 0

    def test_peek_index_increments(self):
        store = PMMemoryStore()
        store.set("a", "alpha")
        store.set("b", "beta")
        _, _, idx_a = store.peek("a")
        _, _, idx_b = store.peek("b")
        assert idx_a == 0
        assert idx_b == 1

    def test_peek_after_update_returns_new_value(self):
        store = PMMemoryStore()
        store.set("k", "old")
        store.set("k", "new")
        hit, value, index = store.peek("k")
        assert hit is True
        assert value == "new"
        assert index == 0  # index unchanged on update


class TestPMMemoryStoreSet:
    def test_set_returns_index(self):
        store = PMMemoryStore()
        idx = store.set("foo", "bar")
        assert idx == 0

    def test_set_second_key_increments_index(self):
        store = PMMemoryStore()
        store.set("x", "1")
        idx = store.set("y", "2")
        assert idx == 1

    def test_set_update_keeps_same_index(self):
        store = PMMemoryStore()
        store.set("k", "v1")
        idx = store.set("k", "v2")
        assert idx == 0

    def test_len_after_sets(self):
        store = PMMemoryStore()
        assert len(store) == 0
        store.set("a", "1")
        assert len(store) == 1
        store.set("b", "2")
        assert len(store) == 2
        store.set("a", "updated")  # update, not new key
        assert len(store) == 2

    def test_contains(self):
        store = PMMemoryStore()
        store.set("present", "yes")
        assert "present" in store
        assert "absent" not in store


class TestPMMemoryStoreFlush:
    def test_flush_clears_all_slots(self):
        store = PMMemoryStore()
        store.set("a", "1")
        store.set("b", "2")
        cleared = store.flush()
        assert cleared == 2
        assert len(store) == 0

    def test_flush_returns_zero_on_empty_store(self):
        store = PMMemoryStore()
        assert store.flush() == 0

    def test_peek_miss_after_flush(self):
        store = PMMemoryStore()
        store.set("k", "v")
        store.flush()
        hit, _, _ = store.peek("k")
        assert hit is False


# ---------------------------------------------------------------------------
# Module-level registry (session isolation)
# ---------------------------------------------------------------------------

class TestSessionIsolation:
    def test_different_sessions_are_independent(self):
        s1 = get_store("session-1")
        s2 = get_store("session-2")
        s1.set("shared_key", "session1_value")

        hit, value, _ = s2.peek("shared_key")
        assert hit is False

    def test_same_session_id_returns_same_store(self):
        s1 = get_store("my-session")
        s1.set("k", "v")
        s2 = get_store("my-session")
        hit, value, _ = s2.peek("k")
        assert hit is True
        assert value == "v"

    def test_drop_store_removes_session(self):
        store = get_store("to-drop")
        store.set("k", "v")
        cleared = drop_store("to-drop")
        assert cleared == 1
        # A new store is created on next access
        new_store = get_store("to-drop")
        hit, _, _ = new_store.peek("k")
        assert hit is False

    def test_drop_nonexistent_session_returns_zero(self):
        assert drop_store("ghost-session") == 0

    def test_silo_size_respected(self):
        store = get_store("sized-session", silo_size=512)
        assert store.silo_size == 512
