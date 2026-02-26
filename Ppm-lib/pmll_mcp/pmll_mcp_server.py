"""
pmll_mcp_server.py — MCP (Model Context Protocol) server for PMLL.

Exposes the Persistent Memory Logic Loop and Q-promise chain operations
as MCP tools that AI agents can invoke.

Adapted from pufferlib/PMLL.py (drQedwards/PufferLib PR #1) and the
Q_promise_lib C library in PPM.

Usage:
    python -m Ppm-lib.pmll_mcp.pmll_mcp_server          # stdio transport
    python -m Ppm-lib.pmll_mcp.pmll_mcp_server --sse     # SSE transport

License: MIT
"""

from __future__ import annotations

import ctypes
import json
import os
import sys
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP

from .pmll_core import (
    MemoryController,
    PythonBackend,
    Promise,
    deterministic_hash,
    make_backend,
)

# ---------------------------------------------------------------------------
# Resolve the Q_promise shared library path
# ---------------------------------------------------------------------------
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_Q_SO_PATH = os.path.join(_REPO_ROOT, "Q_promise_lib", "q_promises.so")

# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------
mcp = FastMCP(
    "pmll-q-promise",
    version="0.1.0",
    description=(
        "Persistent Memory Logic Loop (PMLL) + Q-promise chain — "
        "MCP tool server for AI agents.  Provides memory write/read, "
        "promise processing, utilization queries, hashing, and "
        "Q-promise chain tracing."
    ),
)

# Shared state: one MemoryController per server lifetime
_mc: Optional[MemoryController] = None


def _get_mc() -> MemoryController:
    global _mc
    if _mc is None:
        _mc = MemoryController(pool_size=1024, backend=make_backend(), store_dir=None)
    return _mc


# ── Tool: memory_write ──────────────────────────────────────────────────────
@mcp.tool()
def memory_write(
    pid: int,
    data: str,
    ttl_s: Optional[float] = None,
    importance: Optional[float] = None,
) -> str:
    """Write data into the PMLL promise queue.

    Args:
        pid: Process/promise identifier (integer).
        data: JSON-encoded payload to store.
        ttl_s: Time-to-live in seconds (optional).
        importance: Priority weight 0-1 (optional).

    Returns:
        Confirmation message with the promise id.
    """
    mc = _get_mc()
    try:
        parsed = json.loads(data)
    except (json.JSONDecodeError, TypeError):
        parsed = data
    mc.write(pid=pid, data=parsed, ttl_s=ttl_s, importance=importance)
    return json.dumps({"status": "queued", "pid": pid})


# ── Tool: memory_process ────────────────────────────────────────────────────
@mcp.tool()
def memory_process() -> str:
    """Flush the promise queue into the memory pool.

    Returns:
        Number of promises committed and current utilization.
    """
    mc = _get_mc()
    committed = mc.process_promises()
    return json.dumps({
        "committed": committed,
        "utilization": round(mc.utilization(), 4),
    })


# ── Tool: memory_read ──────────────────────────────────────────────────────
@mcp.tool()
def memory_read(slot: int) -> str:
    """Read the value stored at a specific memory pool slot.

    Args:
        slot: Integer slot index to read.

    Returns:
        JSON-encoded value at the slot, or null if empty.
    """
    mc = _get_mc()
    value = mc.read_slot(slot)
    return json.dumps({"slot": slot, "value": value})


# ── Tool: memory_utilization ────────────────────────────────────────────────
@mcp.tool()
def memory_utilization() -> str:
    """Return the current memory pool utilization (0.0 – 1.0).

    Returns:
        JSON with pool_size and utilization fraction.
    """
    mc = _get_mc()
    return json.dumps({
        "pool_size": mc.pool_size,
        "utilization": round(mc.utilization(), 4),
    })


# ── Tool: memory_snapshot ──────────────────────────────────────────────────
@mcp.tool()
def memory_snapshot() -> str:
    """Return all non-empty slots in the memory pool.

    Returns:
        JSON object mapping slot indices to their stored values.
    """
    mc = _get_mc()
    snap = mc.pool_snapshot()
    # Convert keys to strings for JSON
    return json.dumps({str(k): _safe_serialize(v) for k, v in snap.items()})


# ── Tool: memory_clear ──────────────────────────────────────────────────────
@mcp.tool()
def memory_clear() -> str:
    """Clear all data from the memory pool and promise queue.

    Returns:
        Confirmation message.
    """
    mc = _get_mc()
    mc.clear()
    return json.dumps({"status": "cleared"})


# ── Tool: phi_slot ──────────────────────────────────────────────────────────
@mcp.tool()
def phi_slot(pid: int, pool_size: Optional[int] = None) -> str:
    """Compute the phi slot assignment for a given process id.

    Args:
        pid: Process identifier.
        pool_size: Pool size override (default: server pool size).

    Returns:
        The computed slot index.
    """
    mc = _get_mc()
    n = pool_size if pool_size else mc.pool_size
    slot = mc.backend.phi(pid, n)
    return json.dumps({"pid": pid, "pool_size": n, "slot": slot})


# ── Tool: deterministic_hash ────────────────────────────────────────────────
@mcp.tool()
def hash_payload(payload: str, salt: str = "") -> str:
    """Compute a deterministic SHA-256 hash of a JSON payload.

    Args:
        payload: JSON-encoded data to hash.
        salt: Optional salt string.

    Returns:
        Hex-encoded SHA-256 hash.
    """
    try:
        parsed = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        parsed = payload
    h = deterministic_hash(parsed, salt=salt)
    return json.dumps({"hash": h, "salt": salt})


# ── Tool: q_promise_trace ──────────────────────────────────────────────────
@mcp.tool()
def q_promise_trace(chain_length: int) -> str:
    """Create and trace a Q-promise memory chain (from Q_promise_lib).

    Allocates a linked-list chain of the given length, iterates it via
    q_then(), and returns the resolved entries.

    Args:
        chain_length: Number of nodes in the memory chain (1-10000).

    Returns:
        JSON array of {index, payload} objects for each chain node.
    """
    if chain_length < 0 or chain_length > 10000:
        return json.dumps({"error": "chain_length must be between 0 and 10000"})

    if chain_length == 0:
        return json.dumps([])

    if not os.path.exists(_Q_SO_PATH):
        return json.dumps({"error": f"Q_promise shared library not found at {_Q_SO_PATH}. Run 'make' in Q_promise_lib/ first."})

    lib = ctypes.CDLL(_Q_SO_PATH)
    lib.q_mem_create_chain.argtypes = [ctypes.c_size_t]
    lib.q_mem_create_chain.restype = ctypes.c_void_p
    lib.q_mem_free_chain.argtypes = [ctypes.c_void_p]
    lib.q_mem_free_chain.restype = None

    CALLBACK_TYPE = ctypes.CFUNCTYPE(None, ctypes.c_long, ctypes.c_char_p)
    lib.q_then.argtypes = [ctypes.c_void_p, CALLBACK_TYPE]
    lib.q_then.restype = None

    results: List[Dict[str, Any]] = []

    @CALLBACK_TYPE
    def cb(index, payload):
        results.append({
            "index": index,
            "payload": payload.decode("utf-8") if payload else None,
        })

    head = lib.q_mem_create_chain(chain_length)
    if not head:
        return json.dumps({"error": "Failed to allocate memory chain"})

    try:
        lib.q_then(head, cb)
    finally:
        lib.q_mem_free_chain(head)

    return json.dumps(results)


# ── Tool: q_promise_write ──────────────────────────────────────────────────
@mcp.tool()
def q_promise_write(chain_length: int, ttl_s: float = 60.0) -> str:
    """Trace a Q-promise chain and write each node into the PMLL memory pool.

    This combines Q_promise_lib's memory chain with PMLL's promise system:
    each chain node becomes a promise that gets committed to the pool.

    Args:
        chain_length: Number of Q-promise chain nodes (1-10000).
        ttl_s: Time-to-live for each promise in seconds.

    Returns:
        JSON with number of nodes written, committed, and utilization.
    """
    if chain_length < 0 or chain_length > 10000:
        return json.dumps({"error": "chain_length must be between 0 and 10000"})

    if chain_length == 0:
        return json.dumps({"written": 0, "committed": 0, "utilization": 0.0})

    if not os.path.exists(_Q_SO_PATH):
        return json.dumps({"error": f"Q_promise shared library not found at {_Q_SO_PATH}. Run 'make' in Q_promise_lib/ first."})

    lib = ctypes.CDLL(_Q_SO_PATH)
    lib.q_mem_create_chain.argtypes = [ctypes.c_size_t]
    lib.q_mem_create_chain.restype = ctypes.c_void_p
    lib.q_mem_free_chain.argtypes = [ctypes.c_void_p]
    lib.q_mem_free_chain.restype = None

    CALLBACK_TYPE = ctypes.CFUNCTYPE(None, ctypes.c_long, ctypes.c_char_p)
    lib.q_then.argtypes = [ctypes.c_void_p, CALLBACK_TYPE]
    lib.q_then.restype = None

    mc = _get_mc()
    written = [0]

    @CALLBACK_TYPE
    def cb(index, payload):
        data = payload.decode("utf-8") if payload else None
        mc.write(pid=int(index), data={"q_node": index, "payload": data}, ttl_s=ttl_s)
        written[0] += 1

    head = lib.q_mem_create_chain(chain_length)
    if not head:
        return json.dumps({"error": "Failed to allocate memory chain"})

    try:
        lib.q_then(head, cb)
    finally:
        lib.q_mem_free_chain(head)

    committed = mc.process_promises()

    return json.dumps({
        "written": written[0],
        "committed": committed,
        "utilization": round(mc.utilization(), 4),
    })


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _safe_serialize(obj: Any) -> Any:
    """Best-effort JSON-safe conversion."""
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    if isinstance(obj, dict):
        return {str(k): _safe_serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_safe_serialize(i) for i in obj]
    return str(obj)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    """Run the MCP server (stdio transport by default)."""
    transport = "stdio"
    if "--sse" in sys.argv:
        transport = "sse"
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
