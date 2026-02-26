"""
Tests for the PMLL MCP server — verifying the MCP tool wrappers for
the Persistent Memory Logic Loop (adapted from PufferLib PMLL.py).

Tests:
  1. PMLL core: MemoryController, PythonBackend, Promise, hashing
  2. MCP tool functions: memory_write, memory_read, memory_process, etc.
  3. Q-promise integration via the MCP q_promise_trace/q_promise_write tools
"""
import json
import os
import sys
import time
import pytest

# mcp requires Python >= 3.10
if sys.version_info < (3, 10):
    pytest.skip("mcp requires Python >= 3.10", allow_module_level=True)

# Ensure the repo root is on sys.path so imports work
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "Ppm-lib"))

from pmll_mcp.pmll_core import (
    MemoryController,
    PythonBackend,
    Promise,
    JSONLStore,
    MemoryBlock,
    deterministic_hash,
    make_backend,
    _stable_json_dumps,
)
from pmll_mcp.pmll_mcp_server import (
    memory_write,
    memory_process,
    memory_read,
    memory_utilization,
    memory_snapshot,
    memory_clear,
    phi_slot,
    hash_payload,
    q_promise_trace,
    q_promise_write,
    _get_mc,
)

# Reset the global MemoryController between tests
import pmll_mcp.pmll_mcp_server as _server_mod


@pytest.fixture(autouse=True)
def reset_mc():
    """Reset the global MemoryController before each test."""
    _server_mod._mc = None
    yield
    _server_mod._mc = None


# ---------------------------------------------------------------------------
# PMLL Core tests
# ---------------------------------------------------------------------------
class TestPythonBackend:
    def test_phi_modulo(self):
        b = PythonBackend()
        assert b.phi(10, 7) == 3
        assert b.phi(0, 5) == 0
        assert b.phi(5, 5) == 0

    def test_utilization_clamped(self):
        b = PythonBackend()
        b._util = 1.5
        assert b.utilization() == 1.0
        b._util = -0.5
        assert b.utilization() == 0.0

    def test_process_promise_queue_noop(self):
        b = PythonBackend()
        b.process_promise_queue()  # should not raise


class TestDeterministicHash:
    def test_same_input_same_hash(self):
        h1 = deterministic_hash({"a": 1, "b": 2})
        h2 = deterministic_hash({"b": 2, "a": 1})
        assert h1 == h2

    def test_different_salt_different_hash(self):
        h1 = deterministic_hash("test", salt="a")
        h2 = deterministic_hash("test", salt="b")
        assert h1 != h2


class TestStableJsonDumps:
    def test_sorted_keys(self):
        result = _stable_json_dumps({"z": 1, "a": 2})
        assert result == '{"a":2,"z":1}'


class TestPromise:
    def test_not_expired(self):
        p = Promise(pid=1, data="test", ttl_s=60.0)
        assert not p.expired

    def test_expired(self):
        p = Promise(pid=1, data="test", ttl_s=0.0)
        p.created_ts = time.time() - 1.0
        assert p.expired

    def test_no_ttl_never_expires(self):
        p = Promise(pid=1, data="test", ttl_s=None)
        assert not p.expired


class TestMemoryController:
    def test_write_process_read(self):
        mc = MemoryController(pool_size=64, store_dir=None)
        mc.write(pid=42, data={"hello": "world"}, ttl_s=60.0)
        committed = mc.process_promises()
        assert committed == 1
        slot = mc.backend.phi(42, 64)
        assert mc.read_slot(slot) == {"hello": "world"}

    def test_utilization(self):
        mc = MemoryController(pool_size=10, store_dir=None)
        assert mc.utilization() == 0.0
        mc.write(pid=0, data="a", ttl_s=60.0)
        mc.process_promises()
        assert mc.utilization() == 0.1

    def test_pool_snapshot(self):
        mc = MemoryController(pool_size=16, store_dir=None)
        mc.write(pid=3, data="val", ttl_s=60.0)
        mc.process_promises()
        snap = mc.pool_snapshot()
        assert 3 in snap
        assert snap[3] == "val"

    def test_clear(self):
        mc = MemoryController(pool_size=8, store_dir=None)
        mc.write(pid=1, data="x", ttl_s=60.0)
        mc.process_promises()
        mc.clear()
        assert mc.utilization() == 0.0

    def test_expired_promises_skipped(self):
        mc = MemoryController(pool_size=8, store_dir=None)
        mc.write(pid=1, data="stale", ttl_s=0.0)
        # Force the promise to be expired
        mc._promise_queue[0].created_ts = time.time() - 1.0
        committed = mc.process_promises()
        assert committed == 0

    def test_read_invalid_slot(self):
        mc = MemoryController(pool_size=4, store_dir=None)
        assert mc.read_slot(-1) is None
        assert mc.read_slot(100) is None


class TestJSONLStore:
    def test_append_and_load(self, tmp_path):
        store = JSONLStore(str(tmp_path / "pmll"))
        block = MemoryBlock(payload={"key": "value"}, mid="abc123", ts=1234.0)
        store.append(block)
        loaded = store.load()
        assert len(loaded) == 1
        assert loaded[0].mid == "abc123"

    def test_snapshot_preferred(self, tmp_path):
        store = JSONLStore(str(tmp_path / "pmll"))
        blocks = [
            MemoryBlock(payload={"a": 1}, mid="m1", ts=1.0),
            MemoryBlock(payload={"b": 2}, mid="m2", ts=2.0),
        ]
        store.save_snapshot(blocks)
        # Also append a different block to the log
        store.append(MemoryBlock(payload={"c": 3}, mid="m3", ts=3.0))
        # Snapshot should be preferred
        loaded = store.load()
        assert len(loaded) == 2
        assert loaded[0].mid == "m1"


# ---------------------------------------------------------------------------
# MCP Tool function tests
# ---------------------------------------------------------------------------
class TestMCPToolMemoryWrite:
    def test_write_returns_queued(self):
        result = json.loads(memory_write(pid=1, data='{"test": true}'))
        assert result["status"] == "queued"
        assert result["pid"] == 1

    def test_write_plain_string(self):
        result = json.loads(memory_write(pid=2, data="plain text"))
        assert result["status"] == "queued"


class TestMCPToolMemoryProcess:
    def test_process_empty(self):
        result = json.loads(memory_process())
        assert result["committed"] == 0

    def test_process_after_write(self):
        memory_write(pid=10, data='{"val": 1}', ttl_s=60.0)
        result = json.loads(memory_process())
        assert result["committed"] == 1
        assert result["utilization"] > 0


class TestMCPToolMemoryRead:
    def test_read_empty_slot(self):
        result = json.loads(memory_read(slot=0))
        assert result["value"] is None

    def test_read_after_write_and_process(self):
        mc = _get_mc()
        pid = 5
        slot = mc.backend.phi(pid, mc.pool_size)
        memory_write(pid=pid, data='"hello"', ttl_s=60.0)
        memory_process()
        result = json.loads(memory_read(slot=slot))
        assert result["value"] == "hello"


class TestMCPToolMemoryUtilization:
    def test_utilization_initial(self):
        result = json.loads(memory_utilization())
        assert result["utilization"] == 0.0
        assert result["pool_size"] == 1024


class TestMCPToolMemorySnapshot:
    def test_snapshot_empty(self):
        result = json.loads(memory_snapshot())
        assert result == {}

    def test_snapshot_after_write(self):
        memory_write(pid=7, data='"data"', ttl_s=60.0)
        memory_process()
        result = json.loads(memory_snapshot())
        assert len(result) == 1


class TestMCPToolMemoryClear:
    def test_clear(self):
        memory_write(pid=1, data='"x"', ttl_s=60.0)
        memory_process()
        result = json.loads(memory_clear())
        assert result["status"] == "cleared"
        util = json.loads(memory_utilization())
        assert util["utilization"] == 0.0


class TestMCPToolPhiSlot:
    def test_phi_slot(self):
        result = json.loads(phi_slot(pid=42, pool_size=100))
        assert result["slot"] == 42

    def test_phi_default_pool(self):
        result = json.loads(phi_slot(pid=10))
        assert result["pool_size"] == 1024
        assert result["slot"] == 10


class TestMCPToolHashPayload:
    def test_hash_deterministic(self):
        r1 = json.loads(hash_payload(payload='{"a":1}'))
        r2 = json.loads(hash_payload(payload='{"a":1}'))
        assert r1["hash"] == r2["hash"]

    def test_hash_with_salt(self):
        r1 = json.loads(hash_payload(payload='"test"', salt="s1"))
        r2 = json.loads(hash_payload(payload='"test"', salt="s2"))
        assert r1["hash"] != r2["hash"]


# ---------------------------------------------------------------------------
# MCP Tool: Q-promise integration
# ---------------------------------------------------------------------------
Q_SO_PATH = os.path.join(REPO_ROOT, "Q_promise_lib", "q_promises.so")


@pytest.fixture(scope="session")
def ensure_q_so():
    """Ensure Q_promise shared library is built."""
    import subprocess
    subprocess.check_call(["make", "-C", os.path.join(REPO_ROOT, "Q_promise_lib"), "clean"])
    subprocess.check_call(["make", "-C", os.path.join(REPO_ROOT, "Q_promise_lib")])
    assert os.path.exists(Q_SO_PATH)


class TestMCPToolQPromiseTrace:
    def test_trace_zero(self, ensure_q_so):
        result = json.loads(q_promise_trace(chain_length=0))
        assert result == []

    def test_trace_small_chain(self, ensure_q_so):
        result = json.loads(q_promise_trace(chain_length=5))
        assert len(result) == 5
        assert result[0]["index"] == 0
        assert result[0]["payload"] == "Known"
        assert result[1]["payload"] == "Unknown"

    def test_trace_boundary(self, ensure_q_so):
        result = json.loads(q_promise_trace(chain_length=-1))
        assert "error" in result

    def test_trace_large(self, ensure_q_so):
        result = json.loads(q_promise_trace(chain_length=100))
        assert len(result) == 100


class TestMCPToolQPromiseWrite:
    def test_write_chain(self, ensure_q_so):
        result = json.loads(q_promise_write(chain_length=5, ttl_s=60.0))
        assert result["written"] == 5
        assert result["committed"] > 0
        assert result["utilization"] > 0

    def test_write_zero(self, ensure_q_so):
        result = json.loads(q_promise_write(chain_length=0))
        assert result["written"] == 0
