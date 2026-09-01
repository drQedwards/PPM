"""
kv_store.py — In-process KV slot manager mirroring PMLL memory_silo_t semantics.

**Capacity:** ``silo_size`` is enforced on ``set()``. When the silo is at
capacity and the key is new, the least-recently-used (LRU) slot is evicted
before the insert. Updates to existing keys never grow the silo.

**Concurrency:** stores are process-local. The MCP server assumes a
single-threaded (or externally serialized) event loop; a re-entrant lock
guards the module registry and per-store mutations for light safety.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

_registry_lock = threading.RLock()


@dataclass
class _KVSlot:
    index: int
    key: str
    value: str
    resolved: bool = True
    # Strictly increasing per-store access sequence (not wall/monotonic clock).
    last_accessed: int = 0


class PMMemoryStore:
    """Per-session KV store mirroring PMLL memory_silo_t.

    Eviction strategy when ``len(slots) >= silo_size`` and ``set()`` inserts
    a **new** key: drop the LRU slot (lowest ``last_accessed``), then insert.
    """

    def __init__(self, silo_size: int = 256) -> None:
        self._slots: Dict[str, _KVSlot] = {}
        self.silo_size = max(1, int(silo_size))
        self._lock = threading.RLock()
        self._next_index = 0
        self._access_seq = 0

    def _touch(self, slot: _KVSlot) -> None:
        self._access_seq += 1
        slot.last_accessed = self._access_seq

    def peek(self, key: str) -> Tuple[bool, Optional[str], Optional[int]]:
        with self._lock:
            slot = self._slots.get(key)
            if slot is not None and slot.resolved:
                self._touch(slot)
                return True, slot.value, slot.index
            return False, None, None

    def set(self, key: str, value: str) -> int:
        """Store key/value. New keys at capacity evict the LRU entry."""
        with self._lock:
            if key in self._slots:
                slot = self._slots[key]
                slot.value = value
                slot.resolved = True
                self._touch(slot)
                return slot.index

            if len(self._slots) >= self.silo_size:
                self._evict_lru()

            index = self._next_index
            self._next_index += 1
            slot = _KVSlot(
                index=index,
                key=key,
                value=value,
                resolved=True,
            )
            self._touch(slot)
            self._slots[key] = slot
            return index

    def _evict_lru(self) -> None:
        if not self._slots:
            return
        victim_key = min(self._slots.keys(), key=lambda k: self._slots[k].last_accessed)
        del self._slots[victim_key]

    def flush(self) -> int:
        with self._lock:
            count = len(self._slots)
            self._slots.clear()
            self._next_index = 0
            self._access_seq = 0
            return count

    def __len__(self) -> int:
        with self._lock:
            return len(self._slots)

    def __contains__(self, key: object) -> bool:
        with self._lock:
            return key in self._slots


_session_stores: Dict[str, PMMemoryStore] = {}


def get_store(session_id: str, silo_size: int = 256) -> PMMemoryStore:
    with _registry_lock:
        if session_id not in _session_stores:
            _session_stores[session_id] = PMMemoryStore(silo_size=silo_size)
        return _session_stores[session_id]


def drop_store(session_id: str) -> int:
    with _registry_lock:
        store = _session_stores.pop(session_id, None)
        return len(store) if store is not None else 0


def reset_store(session_id: str, silo_size: int = 256) -> PMMemoryStore:
    """Clear any existing silo for session_id and return a fresh store (clear_on_init)."""
    with _registry_lock:
        _session_stores.pop(session_id, None)
        store = PMMemoryStore(silo_size=silo_size)
        _session_stores[session_id] = store
        return store
