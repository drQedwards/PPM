# cython: language_level=3
# Q_promises.pyx
# Cython bridge exposing the C memory-chain API to Python
from libc.stdlib cimport free
cdef extern from "Q_promises.h":
    cdef struct QMemNode:
        long index
        const char *payload
        QMemNode *next

    QMemNode *q_mem_create_chain(size_t length)
    void q_then(QMemNode *head, void (*cb)(long, const char *))
    void q_mem_free_chain(QMemNode *head)

# -------------------------------------------------------------------
# Internal C callback -> Python trampoline
# -------------------------------------------------------------------
cdef object _py_callback  # Keep a global reference to prevent GC

cdef void _c_callback(long idx, const char *payload) except *:
    # Convert C data to Python and invoke the stored callback
    if _py_callback is not None:
        _py_callback(idx, payload.decode("utf-8") if payload != NULL else None)

# -------------------------------------------------------------------
# Public API
# -------------------------------------------------------------------
def trace(size_t length, callback=None):
    """Iterate over a freshly-created memory chain of `length` nodes.

    Parameters
    ----------
    length : int
        Number of QMemNode elements to allocate.
    callback : Callable[[int, str], None] | None
        Function invoked for each node. If omitted, prints to stdout.
    """
    global _py_callback
    if callback is None:
        # Fallback simple print
        def default_cb(i, s):
            print(f"Memory[{i}] -> {s}")
        _py_callback = default_cb
    else:
        _py_callback = callback

    cdef QMemNode *head = q_mem_create_chain(length)
    if head == NULL:
        raise MemoryError("Failed to allocate memory chain")

    try:
        q_then(head, _c_callback)
    finally:
        q_mem_free_chain(head)
        _py_callback = None
