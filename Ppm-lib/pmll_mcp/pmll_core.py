"""
pmll_core.py — Persistent Memory Logic Loop (core, no torch required).

Adapted from pufferlib/PMLL.py (drQedwards/PufferLib PR #1).
Provides:
  - Stable hashing + JSONL persistence
  - PythonBackend (phi, utilization)
  - Promise queue + MemoryController
  - Backend interface and pure-Python core (Q-promise / Q_promise_lib integration lives in pmll_mcp_server.py)

License: MIT
"""

from __future__ import annotations

import os
import time
import json
import hashlib
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


# =============================================================================
# Utilities: stable hashing + JSONL persistence
# =============================================================================

def _stable_json_dumps(obj: Any) -> str:
    """Deterministic JSON serialisation for hashing."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def deterministic_hash(payload: Any, salt: str = "") -> str:
    h = hashlib.sha256()
    h.update(salt.encode("utf-8"))
    h.update(_stable_json_dumps(payload).encode("utf-8"))
    return h.hexdigest()


@dataclass
class MemoryBlock:
    payload: Dict[str, Any]
    mid: str
    ts: float
    meta: Optional[Dict[str, Any]] = None


class JSONLStore:
    """Append-only log + optional periodic snapshot."""

    def __init__(self, root: str):
        self.root = root
        os.makedirs(root, exist_ok=True)
        self.log_path = os.path.join(root, "pmll_log.jsonl")
        self.snapshot_path = os.path.join(root, "pmll_snapshot.json")

    def append(self, block: MemoryBlock) -> None:
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(_stable_json_dumps(block.__dict__) + "\n")

    def save_snapshot(self, blocks: List[MemoryBlock]) -> None:
        with open(self.snapshot_path, "w", encoding="utf-8") as f:
            f.write(_stable_json_dumps([b.__dict__ for b in blocks]))

    def load(self) -> List[MemoryBlock]:
        if os.path.exists(self.snapshot_path):
            try:
                with open(self.snapshot_path, "r", encoding="utf-8") as f:
                    arr = json.loads(f.read())
                return [MemoryBlock(**x) for x in arr]
            except Exception:
                pass

        blocks: List[MemoryBlock] = []
        if os.path.exists(self.log_path):
            with open(self.log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    blocks.append(MemoryBlock(**json.loads(line)))
        return blocks


# =============================================================================
# Backend interface + pure-Python fallback
# =============================================================================

@runtime_checkable
class PMLLBackend(Protocol):
    def phi(self, idx: int, n: int) -> int: ...
    def process_promise_queue(self) -> None: ...
    def trigger_compression(self, rho: float) -> None: ...
    def utilization(self) -> float: ...


class PythonBackend:
    """Pure-Python fallback backend."""

    def __init__(self):
        self._util = 0.0

    def phi(self, idx: int, n: int) -> int:
        return idx % n

    def process_promise_queue(self) -> None:
        pass

    def trigger_compression(self, rho: float) -> None:
        pass

    def utilization(self) -> float:
        return min(max(self._util, 0.0), 1.0)

    def vectorized_attention(self, q, k, v):
        return None


def make_backend(so_path: Optional[str] = None) -> PythonBackend:
    """Return a PythonBackend (native CTypes backend is not included here)."""
    return PythonBackend()


# =============================================================================
# Promise + MemoryController
# =============================================================================

@dataclass
class Promise:
    pid: int
    data: Any
    ttl_s: Optional[float] = None
    importance: Optional[float] = None
    created_ts: float = field(default_factory=time.time)

    @property
    def expired(self) -> bool:
        if self.ttl_s is None:
            return False
        return (time.time() - self.created_ts) >= self.ttl_s


class MemoryController:
    """
    Thread-safe memory pool with promise queue and persistent storage.
    """

    def __init__(
        self,
        pool_size: int = 1024,
        backend: Optional[PythonBackend] = None,
        store_dir: Optional[str] = None,
        compress_when_util_gt: float = 0.85,
    ):
        self.pool_size = pool_size
        self.backend = backend or make_backend()
        self._pool: List[Any] = [None] * pool_size
        self._promise_queue: List[Promise] = []
        self._lock = threading.Lock()
        self.compress_when_util_gt = compress_when_util_gt

        self.store: Optional[JSONLStore] = None
        if store_dir:
            self.store = JSONLStore(store_dir)

    # --- public API ---

    def write(
        self,
        pid: int,
        data: Any,
        ttl_s: Optional[float] = None,
        importance: Optional[float] = None,
    ) -> None:
        with self._lock:
            self._promise_queue.append(
                Promise(pid=pid, data=data, ttl_s=ttl_s, importance=importance)
            )

    def process_promises(self) -> int:
        """Flush the promise queue into the pool. Returns number committed."""
        with self._lock:
            queue = self._promise_queue[:]
            self._promise_queue.clear()

        committed = 0
        with self._lock:
            for p in queue:
                if p.expired:
                    continue
                slot = self.backend.phi(p.pid, self.pool_size)
                self._pool[slot] = p.data
                committed += 1

                if self.store:
                    block = MemoryBlock(
                        payload={"pid": p.pid, "slot": slot},
                        mid=deterministic_hash({"pid": p.pid, "slot": slot}),
                        ts=time.time(),
                    )
                    self.store.append(block)

            filled = sum(1 for x in self._pool if x is not None)
            current_util = filled / self.pool_size if self.pool_size > 0 else 0.0
            if hasattr(self.backend, "_util"):
                self.backend._util = current_util

            if current_util > self.compress_when_util_gt:
                try:
                    self.backend.trigger_compression(current_util)
                except Exception:
                    self._python_compress()

        return committed

    def read_slot(self, slot: int) -> Any:
        with self._lock:
            if 0 <= slot < self.pool_size:
                return self._pool[slot]
            return None

    def utilization(self) -> float:
        with self._lock:
            filled = sum(1 for x in self._pool if x is not None)
            return filled / self.pool_size if self.pool_size > 0 else 0.0

    def pool_snapshot(self) -> Dict[int, Any]:
        """Return a dict of {slot: data} for all non-None slots."""
        with self._lock:
            return {i: v for i, v in enumerate(self._pool) if v is not None}

    def clear(self) -> None:
        with self._lock:
            self._pool = [None] * self.pool_size
            self._promise_queue.clear()

    def _python_compress(self) -> None:
        """Evict lowest-importance slots (placeholder strategy)."""
        pass
