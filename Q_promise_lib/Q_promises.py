"""Python binding (ctypes) for the PMLL Promise / Continuation Library.

Wraps the C API in ``qpromise.h`` plus the PMLL silo calls it builds on
(``init_silo`` / ``silo_set`` / ``peek`` / ``peek_semantic`` from ``PMLL.h``).
Build the shared library first::

    make -C Q_promise_lib shared        # -> Q_promise_lib/libqpromise.so

or point ``QPROMISE_LIB`` at an existing ``libqpromise.so``.

The library is single-threaded (see Q_promise_lib/README.md): serialize
access yourself. Continuations run only inside :func:`drain`.

Example (the retrieve -> compute -> resolve -> memory loop)::

    from Q_promises import Silo, Promise, drain, PENDING
    silo = Silo(64)
    p = Promise.from_peek(silo, "build:<sha256>")
    if p.state == PENDING:
        p.then(lambda v: print("continuation saw", v))
        p.resolve_commit('{"status": "ok"}')   # resolves + silo_set
        drain()
    silo.peek("build:<sha256>")                 # -> ('{"status": "ok"}', 0)
"""
from __future__ import annotations

import ctypes
import ctypes.util
import os
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

__all__ = [
    "PENDING", "RESOLVED", "REJECTED", "CANCELLED", "STATE_NAMES",
    "QPromiseError", "load_library", "Silo", "Promise", "drain", "jobs_pending",
]
__version__ = "1.1.0"

PENDING, RESOLVED, REJECTED, CANCELLED = 0, 1, 2, 3
STATE_NAMES = {PENDING: "pending", RESOLVED: "resolved", REJECTED: "rejected", CANCELLED: "cancelled"}

_HERE = Path(__file__).resolve().parent
_LIB_NAMES = ("libqpromise.so", "q_promises.so", "libqpromise.dylib")

_c = ctypes.c_void_p
_THEN_FN = ctypes.CFUNCTYPE(_c, ctypes.c_char_p, _c, ctypes.POINTER(_c), ctypes.POINTER(_c))
_FINALLY_FN = ctypes.CFUNCTYPE(None, _c)

_lib: Optional[ctypes.CDLL] = None
_libc = ctypes.CDLL(ctypes.util.find_library("c") or None)
_libc.strdup.restype = _c
_libc.strdup.argtypes = [ctypes.c_char_p]

# ctypes callback objects must outlive the C side's reference to them. They are
# kept here until they have fired and drain() has returned (handlers that never
# fire, e.g. on a cancelled promise, stay registered).
_live_callbacks: Dict[int, object] = {}
_fired: List[int] = []
_next_cb_id = [0]


def _register(make_cb):
    _next_cb_id[0] += 1
    key = _next_cb_id[0]
    cb = make_cb(key)
    _live_callbacks[key] = cb
    return cb


class QPromiseError(RuntimeError):
    """A qpromise_* / silo call reported failure."""


def _enc(s: Optional[str]) -> Optional[bytes]:
    return None if s is None else s.encode("utf-8")


def _dec(b: Optional[bytes]) -> Optional[str]:
    return None if b is None else b.decode("utf-8")


def load_library(path: Optional[str] = None) -> ctypes.CDLL:
    """Load (once) and type the shared library. Search order: ``path``,
    ``$QPROMISE_LIB``, then ``Q_promise_lib/libqpromise.so`` / ``q_promises.so``."""
    global _lib
    if _lib is not None and path is None:
        return _lib
    candidates = [path, os.environ.get("QPROMISE_LIB")] + [str(_HERE / n) for n in _LIB_NAMES]
    found = next((c for c in candidates if c and Path(c).is_file()), None)
    if found is None:
        raise OSError("libqpromise not found; run `make -C Q_promise_lib shared` or set QPROMISE_LIB")
    lib = ctypes.CDLL(found)
    sig = {
        "init_silo": (_c, [ctypes.c_int]),
        "free_silo": (None, [_c]),
        "silo_set": (ctypes.c_int, [_c, ctypes.c_int, ctypes.c_char_p, ctypes.c_char_p]),
        "peek": (ctypes.c_int, [_c, ctypes.c_char_p, ctypes.c_int,
                                ctypes.POINTER(ctypes.c_char_p), ctypes.POINTER(ctypes.c_int)]),
        "peek_semantic": (ctypes.c_int, [_c, ctypes.c_char_p, ctypes.c_float, ctypes.POINTER(ctypes.c_char_p),
                                         ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_float)]),
        "qpromise_create": (_c, []),
        "qpromise_resolved": (_c, [ctypes.c_char_p]),
        "qpromise_rejected": (_c, [ctypes.c_char_p]),
        "qpromise_ref": (None, [_c]),
        "qpromise_unref": (None, [_c]),
        "qpromise_resolve": (ctypes.c_int, [_c, ctypes.c_char_p]),
        "qpromise_reject": (ctypes.c_int, [_c, ctypes.c_char_p]),
        "qpromise_cancel": (ctypes.c_int, [_c]),
        "qpromise_state": (ctypes.c_int, [_c]),
        "qpromise_value": (ctypes.c_char_p, [_c]),
        "qpromise_error": (ctypes.c_char_p, [_c]),
        "qpromise_then": (_c, [_c, _THEN_FN, _c]),
        "qpromise_catch": (_c, [_c, _THEN_FN, _c]),
        "qpromise_finally": (_c, [_c, _FINALLY_FN, _c]),
        "qpromise_drain": (None, []),
        "qpromise_jobs_pending": (ctypes.c_size_t, []),
        "qpromise_bind_pmll": (ctypes.c_int, [_c, _c, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p]),
        "qpromise_pmll_key": (ctypes.c_char_p, [_c]),
        "qpromise_pmll_sat_id": (ctypes.c_int, [_c]),
        "qpromise_pmll_context": (ctypes.c_char_p, [_c]),
        "qpromise_from_peek": (_c, [_c, ctypes.c_char_p]),
        "qpromise_from_peek_semantic": (_c, [_c, ctypes.c_char_p, ctypes.c_float]),
        "qpromise_resolve_commit": (ctypes.c_int, [_c, ctypes.c_char_p, ctypes.c_int]),
    }
    for name, (res, args) in sig.items():
        fn = getattr(lib, name)
        fn.restype, fn.argtypes = res, args
    if path is None:
        _lib = lib
    return lib


class Silo:
    """PMLL ``memory_silo_t`` (owned; freed on :meth:`close` / GC)."""

    def __init__(self, size: int = 256) -> None:
        self._lib = load_library()
        self._ptr = self._lib.init_silo(int(size))
        if not self._ptr:
            raise MemoryError("init_silo failed")
        self.size = int(size)

    def set(self, key: Optional[str], content: str, index: int = -1) -> int:
        """``silo_set``: store at ``index`` (-1 = next free). Returns the slot index."""
        idx = self._lib.silo_set(self._ptr, index, _enc(key), _enc(content))
        if idx < 0:
            raise QPromiseError("silo_set failed (silo full or bad index)")
        return idx

    def peek(self, key: Optional[str] = None, index: int = -1) -> Optional[Tuple[str, int]]:
        """Exact key (or index) lookup. ``(content, index)`` on hit, ``None`` on miss."""
        out, idx = ctypes.c_char_p(), ctypes.c_int(-1)
        if self._lib.peek(self._ptr, _enc(key), index, ctypes.byref(out), ctypes.byref(idx)):
            return _dec(out.value) or "", idx.value
        return None

    def peek_semantic(self, query: str, min_sim: float = 0.5) -> Optional[Tuple[str, int, float]]:
        """Cosine lookup over slot embeddings: ``(content, index, similarity)`` or ``None``."""
        out, idx, sim = ctypes.c_char_p(), ctypes.c_int(-1), ctypes.c_float(0.0)
        if self._lib.peek_semantic(self._ptr, _enc(query), min_sim, ctypes.byref(out),
                                   ctypes.byref(idx), ctypes.byref(sim)):
            return _dec(out.value) or "", idx.value, float(sim.value)
        return None

    def close(self) -> None:
        if getattr(self, "_ptr", None):
            self._lib.free_silo(self._ptr)
            self._ptr = None

    def __del__(self) -> None:  # pragma: no cover - GC timing
        try:
            self.close()
        except Exception:
            pass


def _handler(fn: Callable[[Optional[str]], object]):
    """Wrap a Python callable as a then/catch handler. Its return value is the
    dependent promise's value (str or None); raising rejects it with str(exc).
    Returning a :class:`Promise` makes the dependent adopt that promise."""
    def make(key):
        return _THEN_FN(lambda value, user, out_value, out_error: tramp(key, value, out_value, out_error))

    def tramp(key, value, out_value, out_error):
        _fired.append(key)
        try:
            rv = fn(_dec(value))
        except Exception as exc:  # noqa: BLE001 - surface as rejection
            if out_error:
                out_error[0] = _libc.strdup(str(exc).encode("utf-8"))
            return None
        if isinstance(rv, Promise):
            load_library().qpromise_ref(rv._ptr)  # transfer one ref to the library
            return rv._ptr
        if rv is not None and out_value:
            out_value[0] = _libc.strdup(str(rv).encode("utf-8"))
        return None
    return _register(make)


class Promise:
    """A ``qpromise_t`` handle (one reference; released on GC / :meth:`release`)."""

    def __init__(self, ptr: int) -> None:
        if not ptr:
            raise MemoryError("qpromise allocation failed")
        self._lib = load_library()
        self._ptr = ptr

    # -- constructors ------------------------------------------------------
    @classmethod
    def create(cls) -> "Promise":
        return cls(load_library().qpromise_create())

    @classmethod
    def resolved(cls, value: Optional[str]) -> "Promise":
        return cls(load_library().qpromise_resolved(_enc(value)))

    @classmethod
    def rejected(cls, error: str) -> "Promise":
        return cls(load_library().qpromise_rejected(_enc(error)))

    @classmethod
    def from_peek(cls, silo: Silo, key: str) -> "Promise":
        """Hit: RESOLVED with the stored content. Miss: PENDING bound to ``key``."""
        return cls(load_library().qpromise_from_peek(silo._ptr, _enc(key)))

    @classmethod
    def from_peek_semantic(cls, silo: Silo, query: str, min_sim: float = 0.5) -> "Promise":
        return cls(load_library().qpromise_from_peek_semantic(silo._ptr, _enc(query), min_sim))

    # -- state -------------------------------------------------------------
    @property
    def state(self) -> int:
        return self._lib.qpromise_state(self._ptr)

    @property
    def state_name(self) -> str:
        return STATE_NAMES.get(self.state, "unknown")

    @property
    def value(self) -> Optional[str]:
        return _dec(self._lib.qpromise_value(self._ptr))

    @property
    def error(self) -> Optional[str]:
        return _dec(self._lib.qpromise_error(self._ptr))

    @property
    def pmll_key(self) -> Optional[str]:
        return _dec(self._lib.qpromise_pmll_key(self._ptr))

    @property
    def pmll_sat_id(self) -> int:
        return self._lib.qpromise_pmll_sat_id(self._ptr)

    @property
    def pmll_context(self) -> Optional[str]:
        return _dec(self._lib.qpromise_pmll_context(self._ptr))

    # -- settle (False if the promise was not pending) -----------------------
    def resolve(self, value: Optional[str]) -> bool:
        return self._lib.qpromise_resolve(self._ptr, _enc(value)) == 0

    def reject(self, error: str) -> bool:
        return self._lib.qpromise_reject(self._ptr, _enc(error)) == 0

    def cancel(self) -> bool:
        return self._lib.qpromise_cancel(self._ptr) == 0

    def bind_pmll(self, silo: Silo, key: str, sat_state_id: int = -1, context: Optional[str] = None) -> bool:
        return self._lib.qpromise_bind_pmll(self._ptr, silo._ptr, _enc(key), sat_state_id, _enc(context)) == 0

    def resolve_commit(self, value: str, silo_index: int = -1) -> bool:
        """Resolve and ``silo_set`` under the bound key (promise -> memory update)."""
        return self._lib.qpromise_resolve_commit(self._ptr, _enc(value), silo_index) == 0

    # -- chaining (handlers run during drain()) ------------------------------
    def then(self, fn: Callable[[Optional[str]], object]) -> "Promise":
        return Promise(self._lib.qpromise_then(self._ptr, _handler(fn), None))

    def catch(self, fn: Callable[[Optional[str]], object]) -> "Promise":
        return Promise(self._lib.qpromise_catch(self._ptr, _handler(fn), None))

    def finally_(self, fn: Callable[[], None]) -> "Promise":
        def make(key):
            def tramp(_user):
                _fired.append(key)
                fn()
            return _FINALLY_FN(tramp)
        cb = _register(make)
        return Promise(self._lib.qpromise_finally(self._ptr, cb, None))

    def release(self) -> None:
        if getattr(self, "_ptr", None):
            self._lib.qpromise_unref(self._ptr)
            self._ptr = None

    def __del__(self) -> None:  # pragma: no cover - GC timing
        try:
            self.release()
        except Exception:
            pass

    def __repr__(self) -> str:
        return f"<Promise {self.state_name} value={self.value!r} error={self.error!r}>"


def drain() -> None:
    """Run queued continuations (``qpromise_drain``)."""
    load_library().qpromise_drain()
    while _fired:
        _live_callbacks.pop(_fired.pop(), None)


def jobs_pending() -> int:
    return int(load_library().qpromise_jobs_pending())
