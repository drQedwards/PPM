"""
pmll_mcp_server.py — MCP (Model Context Protocol) server for PMLL.

Exposes the Persistent Memory Logic Loop and Q-promise chain operations
as MCP tools that AI agents can invoke.

Adapted from pufferlib/PMLL.py (drQedwards/PufferLib PR #1) and the
Q_promise_lib C library in PPM.

Usage:
    python -m pmll_mcp.pmll_mcp_server          # stdio transport
    python -m pmll_mcp.pmll_mcp_server --sse     # SSE transport

License: MIT
"""

from __future__ import annotations

import ctypes
import json
import os
import sys
from typing import Any, Dict, List, Optional

try:
    from mcp.server.mcpserver import MCPServer as _MCPServer
except ModuleNotFoundError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _MCPServer

from .pmll_core import (
    MemoryController,
    deterministic_hash,
    make_backend,
)

# ---------------------------------------------------------------------------
# Resolve the Q_promise shared library path
# ---------------------------------------------------------------------------
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_Q_LIB_DIR = os.path.join(_REPO_ROOT, "Q_promise_lib")
_Q_SO_CANDIDATES = ("libqpromise.so", "q_promises.so")


def _resolve_q_so_path():
    """Prefer canonical libqpromise.so; fall back to legacy q_promises.so."""
    env = os.environ.get("PMLL_Q_PROMISE_SO")
    if env:
        return env
    for name in _Q_SO_CANDIDATES:
        path = os.path.join(_Q_LIB_DIR, name)
        if os.path.isfile(path):
            return path
    return os.path.join(_Q_LIB_DIR, _Q_SO_CANDIDATES[0])


_Q_SO_PATH = _resolve_q_so_path()
_MAX_CHAIN_LENGTH = 10000

# Cached ctypes library handle (lazy-loaded on first use)
_q_lib = None
_q_cb_type = None

# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------
mcp = _MCPServer(
    "pmll-q-promise",
    instructions=(
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


def _q_so_missing_msg() -> str:
    return (
        f"Q_promise shared library not found at {_Q_SO_PATH}. "
        "Run 'make' in Q_promise_lib/ first."
    )


def _demo_payload(index: int) -> bytes:
    """Seed-compatible demo payloads: index 0 is Known, rest Unknown."""
    return b"Known" if index == 0 else b"Unknown"


# ── Tool: q_promise_trace ──────────────────────────────────────────────────
@mcp.tool()
def q_promise_trace(chain_length: int) -> str:
    """Create and trace resolved Q-promises via libqpromise (Q_promise_lib).

    Builds ``chain_length`` resolved promises through the ``qpromise_*`` C API
    (replacing the removed QMemNode ``q_mem_create_chain`` / ``q_then`` walker).
    Demo payloads keep the seed convention: index 0 → "Known", else "Unknown".

    Args:
        chain_length: Number of promises to create (0-10000).
            If 0, an empty JSON array is returned.

    Returns:
        JSON array of {index, payload} objects, or an empty JSON array if
        ``chain_length`` is 0.
    """
    if chain_length < 0 or chain_length > _MAX_CHAIN_LENGTH:
        return json.dumps({
            "error": f"chain_length must be between 0 and {_MAX_CHAIN_LENGTH}"
        })

    if chain_length == 0:
        return json.dumps([])

    lib = _load_q_lib()
    if lib is None:
        return json.dumps({"error": _q_so_missing_msg()})

    results: List[Dict[str, Any]] = []
    for index in range(chain_length):
        promise = lib.qpromise_resolved(_demo_payload(index))
        if not promise:
            return json.dumps({"error": "Failed to allocate promise"})
        try:
            raw = lib.qpromise_value(promise)
            results.append({
                "index": index,
                "payload": raw.decode("utf-8") if raw else None,
            })
        finally:
            lib.qpromise_unref(promise)

    return json.dumps(results)


# ── Tool: q_promise_write ──────────────────────────────────────────────────
@mcp.tool()
def q_promise_write(chain_length: int, ttl_s: float = 60.0) -> str:
    """Resolve Q-promises and write each into the PMLL memory pool.

    Uses libqpromise to create resolved promises, then queues them through
    PMLL's MemoryController (write → process_promises).

    Args:
        chain_length: Number of Q-promises to create (0-10000).
        ttl_s: Time-to-live for each promise in seconds.

    Returns:
        JSON with number of nodes written, committed, and utilization.
    """
    if chain_length < 0 or chain_length > _MAX_CHAIN_LENGTH:
        return json.dumps({
            "error": f"chain_length must be between 0 and {_MAX_CHAIN_LENGTH}"
        })

    if chain_length == 0:
        return json.dumps({"written": 0, "committed": 0, "utilization": 0.0})

    lib = _load_q_lib()
    if lib is None:
        return json.dumps({"error": _q_so_missing_msg()})

    mc = _get_mc()
    written = 0

    for index in range(chain_length):
        promise = lib.qpromise_resolved(_demo_payload(index))
        if not promise:
            return json.dumps({"error": "Failed to allocate promise"})
        try:
            raw = lib.qpromise_value(promise)
            payload = raw.decode("utf-8") if raw else None
            mc.write(
                pid=int(index),
                data={"q_node": index, "payload": payload},
                ttl_s=ttl_s,
            )
            written += 1
        finally:
            lib.qpromise_unref(promise)

    committed = mc.process_promises()

    return json.dumps({
        "written": written,
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


def _load_q_lib():
    """Lazily load and cache libqpromise (qpromise_* C API)."""
    global _q_lib, _q_cb_type, _Q_SO_PATH
    if _q_lib is not None:
        return _q_lib

    _Q_SO_PATH = _resolve_q_so_path()
    if not os.path.isfile(_Q_SO_PATH):
        return None

    lib = ctypes.CDLL(_Q_SO_PATH)
    lib.qpromise_resolved.argtypes = [ctypes.c_char_p]
    lib.qpromise_resolved.restype = ctypes.c_void_p
    lib.qpromise_value.argtypes = [ctypes.c_void_p]
    lib.qpromise_value.restype = ctypes.c_char_p
    lib.qpromise_unref.argtypes = [ctypes.c_void_p]
    lib.qpromise_unref.restype = None

    _q_lib = lib
    _q_cb_type = None  # old QThenCallback removed with q_mem_* API
    return lib


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
