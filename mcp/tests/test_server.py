"""
tests/test_server.py — Smoke tests for the MCP tool functions in server.py.

These tests call the underlying tool functions directly (bypassing the MCP
transport layer) to verify request/response semantics without requiring a
running MCP server.
"""

import sys
import os

import pytest

MCP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, MCP_DIR)

# Reset module-level state between tests
import pmll_memory_mcp.server as _server_mod
from pmll_memory_mcp.kv_store import _session_stores
from pmll_memory_mcp.server import (
    init,
    peek,
    set,
    resolve,
    flush,
    _promise_registry,
    _active_sessions,
)


@pytest.fixture(autouse=True)
def reset_state():
    """Reset all module-level state before each test."""
    _session_stores.clear()
    _active_sessions.clear()
    # Clear the shared promise registry
    _promise_registry._promises.clear()
    yield
    _session_stores.clear()
    _active_sessions.clear()
    _promise_registry._promises.clear()


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------

class TestInit:
    def test_init_returns_initialized(self):
        result = init(session_id="s1")
        assert result["status"] == "initialized"
        assert result["session_id"] == "s1"
        assert result["silo_size"] == 256  # default

    def test_init_custom_silo_size(self):
        result = init(session_id="s2", silo_size=512)
        assert result["silo_size"] == 512

    def test_init_registers_session(self):
        init(session_id="s3")
        assert "s3" in _active_sessions


# ---------------------------------------------------------------------------
# set + peek
# ---------------------------------------------------------------------------

class TestSetAndPeek:
    def test_peek_miss_before_set(self):
        init(session_id="sx")
        result = peek(session_id="sx", key="missing")
        assert result["hit"] is False

    def test_set_then_peek_hit(self):
        init(session_id="sa")
        set_result = set(session_id="sa", key="url", value="https://example.com")
        assert set_result["status"] == "stored"
        assert isinstance(set_result["index"], int)

        peek_result = peek(session_id="sa", key="url")
        assert peek_result["hit"] is True
        assert peek_result["value"] == "https://example.com"

    def test_set_returns_incrementing_index(self):
        init(session_id="sb")
        r1 = set(session_id="sb", key="k1", value="v1")
        r2 = set(session_id="sb", key="k2", value="v2")
        assert r1["index"] == 0
        assert r2["index"] == 1


# ---------------------------------------------------------------------------
# resolve
# ---------------------------------------------------------------------------

class TestResolve:
    def test_resolve_unknown_promise_returns_pending(self):
        result = resolve(session_id="sr", promise_id="ghost")
        assert result["status"] == "pending"
        assert result["payload"] is None

    def test_resolve_registered_and_resolved_promise(self):
        _promise_registry.register("p1")
        _promise_registry.resolve("p1", "some-payload")
        result = resolve(session_id="sr", promise_id="p1")
        assert result["status"] == "resolved"
        assert result["payload"] == "some-payload"

    def test_resolve_pending_promise(self):
        _promise_registry.register("p2")
        result = resolve(session_id="sr", promise_id="p2")
        assert result["status"] == "pending"
        assert result["payload"] is None

    def test_peek_returns_pending_for_in_flight_promise(self):
        init(session_id="sp")
        _promise_registry.register("async-key")
        result = peek(session_id="sp", key="async-key")
        assert result["hit"] is True
        assert result["status"] == "pending"


# ---------------------------------------------------------------------------
# flush
# ---------------------------------------------------------------------------

class TestFlush:
    def test_flush_clears_slots(self):
        init(session_id="sf")
        set(session_id="sf", key="a", value="1")
        set(session_id="sf", key="b", value="2")
        result = flush(session_id="sf")
        assert result["status"] == "flushed"
        assert result["cleared_count"] == 2

    def test_flush_removes_session_from_active(self):
        init(session_id="sf2")
        flush(session_id="sf2")
        assert "sf2" not in _active_sessions

    def test_peek_miss_after_flush(self):
        init(session_id="sf3")
        set(session_id="sf3", key="k", value="v")
        flush(session_id="sf3")
        result = peek(session_id="sf3", key="k")
        assert result["hit"] is False

    def test_flush_nonexistent_session_returns_zero(self):
        result = flush(session_id="ghost-session")
        assert result["status"] == "flushed"
        assert result["cleared_count"] == 0


# ---------------------------------------------------------------------------
# Session isolation
# ---------------------------------------------------------------------------

class TestSessionIsolation:
    def test_two_sessions_dont_share_kv(self):
        init(session_id="sess-A")
        init(session_id="sess-B")
        set(session_id="sess-A", key="shared", value="A-value")
        result = peek(session_id="sess-B", key="shared")
        assert result["hit"] is False
