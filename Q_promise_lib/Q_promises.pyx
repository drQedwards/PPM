# cython: language_level=3
# distutils: sources = Q_promise_lib/qpromise.c PMLL.c
# distutils: include_dirs = Q_promise_lib .
# distutils: define_macros = PMLL_NO_MAIN=1
"""Cython binding for the PMLL Promise / Continuation Library (qpromise.h).

Same public surface as the ctypes binding in Q_promises.py (Silo, Promise,
drain, jobs_pending, PENDING/RESOLVED/REJECTED/CANCELLED), but compiled
against qpromise.c + PMLL.c directly, so no libqpromise.so is needed.

Build (from the repo root)::

    cythonize -i -3 Q_promise_lib/Q_promises.pyx

Single-threaded, like the C library: continuations run inside drain().
"""
from cpython.ref cimport PyObject, Py_INCREF, Py_DECREF
from libc.string cimport strdup

cdef extern from "PMLL.h":
    ctypedef struct memory_silo_t:
        int size
        int slot_count
    memory_silo_t *init_silo(int size)
    void free_silo(memory_silo_t *silo)
    int silo_set(memory_silo_t *silo, int index, const char *key, const char *content)
    int peek(memory_silo_t *silo, const char *key, int index, const char **out_value, int *out_index)
    int peek_semantic(memory_silo_t *silo, const char *query, float min_sim,
                      const char **out_value, int *out_index, float *out_sim)

cdef extern from "qpromise.h":
    ctypedef struct qpromise_t:
        pass
    ctypedef qpromise_t *(*qpromise_then_fn)(const char *value, void *user,
                                            char **out_value, char **out_error) noexcept
    ctypedef void (*qpromise_finally_fn)(void *user) noexcept
    qpromise_t *qpromise_create()
    qpromise_t *qpromise_resolved(const char *value)
    qpromise_t *qpromise_rejected(const char *error)
    void qpromise_ref(qpromise_t *p)
    void qpromise_unref(qpromise_t *p)
    int qpromise_resolve(qpromise_t *p, const char *value)
    int qpromise_reject(qpromise_t *p, const char *error)
    int qpromise_cancel(qpromise_t *p)
    int qpromise_state(const qpromise_t *p)
    const char *qpromise_value(const qpromise_t *p)
    const char *qpromise_error(const qpromise_t *p)
    qpromise_t *qpromise_then(qpromise_t *p, qpromise_then_fn fn, void *user)
    qpromise_t *qpromise_catch(qpromise_t *p, qpromise_then_fn fn, void *user)
    qpromise_t *qpromise_finally(qpromise_t *p, qpromise_finally_fn fn, void *user)
    void qpromise_drain()
    size_t qpromise_jobs_pending()
    int qpromise_bind_pmll(qpromise_t *p, memory_silo_t *silo, const char *memory_key,
                           int sat_state_id, const char *context)
    const char *qpromise_pmll_key(const qpromise_t *p)
    int qpromise_pmll_sat_id(const qpromise_t *p)
    const char *qpromise_pmll_context(const qpromise_t *p)
    qpromise_t *qpromise_from_peek(memory_silo_t *silo, const char *key)
    qpromise_t *qpromise_from_peek_semantic(memory_silo_t *silo, const char *query, float min_sim)
    int qpromise_resolve_commit(qpromise_t *p, const char *value, int silo_index)

cdef class Promise

PENDING, RESOLVED, REJECTED, CANCELLED = 0, 1, 2, 3
STATE_NAMES = {PENDING: "pending", RESOLVED: "resolved", REJECTED: "rejected", CANCELLED: "cancelled"}


class QPromiseError(RuntimeError):
    """A qpromise_* / silo call reported failure."""


cdef bytes _b(s):
    return None if s is None else s.encode("utf-8")


cdef const char *_cs(bytes b):
    if b is None:
        return NULL
    return <const char *> b


cdef object _s(const char *p):
    return None if p == NULL else p.decode("utf-8")


cdef class Silo:
    """PMLL memory_silo_t (owned)."""
    cdef memory_silo_t *_ptr
    cdef readonly int size

    def __cinit__(self, int size=256):
        self._ptr = init_silo(size)
        if self._ptr == NULL:
            raise MemoryError("init_silo failed")
        self.size = size

    def __dealloc__(self):
        if self._ptr != NULL:
            free_silo(self._ptr)
            self._ptr = NULL

    def set(self, key, str content, int index=-1):
        cdef bytes bk = _b(key)
        cdef bytes bc = _b(content)
        cdef int idx = silo_set(self._ptr, index, _cs(bk), _cs(bc))
        if idx < 0:
            raise QPromiseError("silo_set failed (silo full or bad index)")
        return idx

    def peek(self, key=None, int index=-1):
        cdef bytes bk = _b(key)
        cdef const char *out = NULL
        cdef int idx = -1
        if peek(self._ptr, _cs(bk), index, &out, &idx):
            return (_s(out) or "", idx)
        return None

    def peek_semantic(self, str query, float min_sim=0.5):
        cdef bytes bq = _b(query)
        cdef const char *out = NULL
        cdef int idx = -1
        cdef float sim = 0
        if peek_semantic(self._ptr, _cs(bq), min_sim, &out, &idx, &sim):
            return (_s(out) or "", idx, float(sim))
        return None


cdef qpromise_t *_then_tramp(const char *value, void *user,
                             char **out_value, char **out_error) noexcept with gil:
    cdef object fn = <object> user
    cdef bytes b
    cdef Promise adopted
    try:
        try:
            rv = fn(_s(value))
        except Exception as exc:
            if out_error != NULL:
                b = str(exc).encode("utf-8")
                out_error[0] = strdup(b)
            return NULL
        if isinstance(rv, Promise):
            adopted = <Promise> rv
            qpromise_ref(adopted._ptr)
            return adopted._ptr
        if rv is not None and out_value != NULL:
            b = str(rv).encode("utf-8")
            out_value[0] = strdup(b)
        return NULL
    finally:
        Py_DECREF(fn)  # handlers run at most once


cdef void _finally_tramp(void *user) noexcept with gil:
    cdef object fn = <object> user
    try:
        fn()
    except Exception:
        pass
    finally:
        Py_DECREF(fn)


cdef Promise _wrap(qpromise_t *p):
    if p == NULL:
        raise MemoryError("qpromise allocation failed")
    cdef Promise o = Promise.__new__(Promise)
    o._ptr = p
    return o


cdef class Promise:
    """A qpromise_t handle holding one reference."""
    cdef qpromise_t *_ptr

    def __dealloc__(self):
        if self._ptr != NULL:
            qpromise_unref(self._ptr)
            self._ptr = NULL

    @staticmethod
    def create():
        return _wrap(qpromise_create())

    @staticmethod
    def resolved(value):
        cdef bytes b = _b(value)
        return _wrap(qpromise_resolved(_cs(b)))

    @staticmethod
    def rejected(str error):
        cdef bytes b = _b(error)
        return _wrap(qpromise_rejected(_cs(b)))

    @staticmethod
    def from_peek(Silo silo, str key):
        cdef bytes b = _b(key)
        return _wrap(qpromise_from_peek(silo._ptr, _cs(b)))

    @staticmethod
    def from_peek_semantic(Silo silo, str query, float min_sim=0.5):
        cdef bytes b = _b(query)
        return _wrap(qpromise_from_peek_semantic(silo._ptr, _cs(b), min_sim))

    @property
    def state(self):
        return qpromise_state(self._ptr)

    @property
    def state_name(self):
        return STATE_NAMES.get(qpromise_state(self._ptr), "unknown")

    @property
    def value(self):
        return _s(qpromise_value(self._ptr))

    @property
    def error(self):
        return _s(qpromise_error(self._ptr))

    @property
    def pmll_key(self):
        return _s(qpromise_pmll_key(self._ptr))

    @property
    def pmll_sat_id(self):
        return qpromise_pmll_sat_id(self._ptr)

    @property
    def pmll_context(self):
        return _s(qpromise_pmll_context(self._ptr))

    def resolve(self, value):
        cdef bytes b = _b(value)
        return qpromise_resolve(self._ptr, _cs(b)) == 0

    def reject(self, str error):
        cdef bytes b = _b(error)
        return qpromise_reject(self._ptr, _cs(b)) == 0

    def cancel(self):
        return qpromise_cancel(self._ptr) == 0

    def bind_pmll(self, Silo silo, str key, int sat_state_id=-1, context=None):
        cdef bytes bk = _b(key)
        cdef bytes bc = _b(context)
        return qpromise_bind_pmll(self._ptr, silo._ptr, _cs(bk), sat_state_id, _cs(bc)) == 0

    def resolve_commit(self, str value, int silo_index=-1):
        cdef bytes b = _b(value)
        return qpromise_resolve_commit(self._ptr, _cs(b), silo_index) == 0

    def then(self, fn):
        Py_INCREF(fn)
        cdef qpromise_t *c = qpromise_then(self._ptr, _then_tramp, <void *> fn)
        if c == NULL:
            Py_DECREF(fn)
        return _wrap(c)

    def catch(self, fn):
        Py_INCREF(fn)
        cdef qpromise_t *c = qpromise_catch(self._ptr, _then_tramp, <void *> fn)
        if c == NULL:
            Py_DECREF(fn)
        return _wrap(c)

    def finally_(self, fn):
        Py_INCREF(fn)
        cdef qpromise_t *c = qpromise_finally(self._ptr, _finally_tramp, <void *> fn)
        if c == NULL:
            Py_DECREF(fn)
        return _wrap(c)

    def release(self):
        if self._ptr != NULL:
            qpromise_unref(self._ptr)
            self._ptr = NULL

    def __repr__(self):
        return f"<Promise {self.state_name} value={self.value!r} error={self.error!r}>"


def drain():
    """Run queued continuations (qpromise_drain)."""
    qpromise_drain()


def jobs_pending():
    return int(qpromise_jobs_pending())
