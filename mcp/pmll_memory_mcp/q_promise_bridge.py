"""
q_promise_bridge.py — In-process registry for in-flight Q-promise work.

A small pure-Python model of the promise lifecycle in Q_promise_lib
(``qpromise.h``): an entry starts ``"pending"`` and becomes ``"resolved"``
once ``resolve()`` stores a payload. It does not call the C library, and it
only models PENDING -> RESOLVED; the C API also has REJECTED / CANCELLED and
then / catch / finally continuations that run in ``qpromise_drain()``.

For the real C library use the bindings in ``Q_promise_lib/Q_promises.py``
(ctypes over ``libqpromise.so``) or ``Q_promise_lib/Q_promises.pyx`` (Cython).
The older ``QMemNode`` / ``q_mem_create_chain`` / ``q_then`` chain API that
this module used to describe was removed from Q_promise_lib.

``peek_promise()`` is a non-destructive status check.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class _QPromise:
    """One promise entry (a pending or resolved unit of work).

    Fields:
      - promise_id  → logical identifier (callers namespace it, e.g. ``"{session}:{key}"``)
      - status      → ``"pending"`` | ``"resolved"`` (QPROMISE_PENDING / QPROMISE_RESOLVED)
      - payload     → resolved data string, or None while pending
    """

    promise_id: str
    status: str = "pending"  # "pending" | "resolved"
    payload: Optional[str] = None


class QPromiseRegistry:
    """In-process registry of Q-promise continuations.

    Models the pending -> resolved part of the C ``qpromise_t`` lifecycle:
      - ``register()``      — allocate a new pending node
      - ``resolve()``       — store the payload (like ``qpromise_resolve``)
      - ``peek_promise()``  — read status without consuming the entry

    Multiple sessions share a single registry; the ``promise_id`` is the
    caller's responsibility to namespace (e.g. ``"{session_id}:{key}"``).
    """

    def __init__(self) -> None:
        self._promises: Dict[str, _QPromise] = {}
        # MCP 2.x runs sync tools in worker threads; keep each operation atomic.
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def register(self, promise_id: str) -> None:
        """Add a new pending promise (like ``qpromise_create``)."""
        with self._lock:
            self._promises[promise_id] = _QPromise(promise_id=promise_id)

    def resolve(self, promise_id: str, payload: str) -> bool:
        """Mark *promise_id* as resolved with *payload*.

        Like ``qpromise_resolve``; there are no continuations to run here.

        Returns:
            True if the promise existed and was resolved; False if unknown.
        """
        with self._lock:
            promise = self._promises.get(promise_id)
            if promise is None:
                return False
            promise.status = "resolved"
            promise.payload = payload
            return True

    def peek_promise(
        self, promise_id: str
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """Non-destructive status check.

        Returns:
            (found, status, payload) — ``found`` is False when the promise
            ID is unknown.
        """
        with self._lock:
            promise = self._promises.get(promise_id)
            if promise is None:
                return False, None, None
            return True, promise.status, promise.payload

    # ------------------------------------------------------------------
    # Introspection helpers
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._promises)

    def __contains__(self, promise_id: object) -> bool:
        return promise_id in self._promises
