# PMLL Promise / Continuation Library (Q-promise)

Temporal / control-flow layer for **PMLL**. Promises track unresolved work and
continuations; **PMLL** owns durable memory/state (silo, `peek`,
`peek_semantic`, SAT bridge, `init_pml`).

> Q-promise does **not** replace or duplicate the silo. A promise may
> *reference* a memory key and optional SAT state id; results are committed
> back with `silo_set` / `qpromise_resolve_commit`.

## Concepts

| Term | Role |
|------|------|
| **Promise** | Explicit state machine: `PENDING → RESOLVED(value) \| REJECTED(error) \| CANCELLED` |
| **Continuation** | `then` / `catch` / `finally` handler; runs **at most once** |
| **Scheduler** | Internal job queue drained by `qpromise_drain()` — isolated from the promise API |
| **PMLL memory** | `memory_silo_t` via `silo_set` / `peek` / `peek_semantic` |
| **PMLL SAT state** | Optional integer id bound on a promise (`qpromise_bind_pmll`); not a second memory store |

## Intended loop

```
PMLL memory/state
  → initiate operation (qpromise_from_peek / create)
  → Q-promise unresolved work (PENDING)
  → completion (resolve / resolve_commit)
  → continuation (then/catch/finally via qpromise_drain)
  → result committed to PMLL memory
  → next retrieve
  → loop
```

Example: semantic or exact peek; on hit resolve immediately; on miss stay
pending, do work, `qpromise_resolve_commit`, fire continuations.

## Thread safety

**Single-threaded.** All API calls on a given process heap must be externally
serialized. This implementation does not create threads and is not internally
thread-safe. Continuations run only during `qpromise_drain()` on the calling
thread.

## Build & test

```bash
cd Q_promise_lib
make clean && make test          # deterministic C suite
make test-asan                   # if gcc supports AddressSanitizer
make shared                      # libqpromise.so (+ optional q_promises.so alias)
```

`make test` links `../PMLL.c` with `-DPMLL_NO_MAIN`. No network / external
services.

## C API (prefix `qpromise_*`)

```c
qpromise_t *qpromise_create(void);
qpromise_t *qpromise_resolved(const char *value);
qpromise_t *qpromise_rejected(const char *error);
int qpromise_resolve(qpromise_t *p, const char *value);
int qpromise_reject(qpromise_t *p, const char *error);
int qpromise_cancel(qpromise_t *p);
qpromise_state_t qpromise_state(const qpromise_t *p);

qpromise_t *qpromise_then(qpromise_t *p, qpromise_then_fn fn, void *user);
qpromise_t *qpromise_catch(qpromise_t *p, qpromise_catch_fn fn, void *user);
qpromise_t *qpromise_finally(qpromise_t *p, qpromise_finally_fn fn, void *user);
void qpromise_drain(void);

int qpromise_bind_pmll(qpromise_t *p, memory_silo_t *silo,
                       const char *memory_key, int sat_state_id,
                       const char *context);
qpromise_t *qpromise_from_peek(memory_silo_t *silo, const char *key);
qpromise_t *qpromise_from_peek_semantic(memory_silo_t *silo,
                                        const char *query, float min_sim);
int qpromise_resolve_commit(qpromise_t *p, const char *value, int silo_index);

void qpromise_ref(qpromise_t *p);
void qpromise_unref(qpromise_t *p);
```

Opaque `qpromise_t`. Every allocation has a failure path (`NULL` / `-1`).
Caller owns one ref on returned promises; continuations hold refs to children
until freed with the parent.

Handlers may return another promise (adoption) or set `*out_value` /
`*out_error` (ownership transfers to the library). Rejection propagates through
`then` until `catch`. Cancel skips `then`/`catch` but still runs `finally`.
Repeated resolve/reject/cancel on a non-pending promise fails without changing
state.

## Breaking changes vs seed

The seed (`QMemNode` / `q_mem_create_chain` / `q_then`) was a linked-list
“memory chain” walker with Known/Unknown payloads — **not** a promise. That
API is removed. `Promises.c` is now a small demo of the new API.
`Q_promises.h` is a compatibility include redirecting to `qpromise.h`.
Independent of FastMCP / MCPServer.

## Python bindings

Two bindings expose the same API (`Silo`, `Promise`, `drain`, `jobs_pending`,
`PENDING` / `RESOLVED` / `REJECTED` / `CANCELLED`):

| File | How | Build |
|------|-----|-------|
| `Q_promises.py` | ctypes over `libqpromise.so` (or `$QPROMISE_LIB`) | `make shared` |
| `Q_promises.pyx` | Cython, compiles `qpromise.c` + `../PMLL.c` in | see `tests/test_q_promises_binding.py` |

```python
from Q_promises import Silo, Promise, drain, PENDING
silo = Silo(64)
p = Promise.from_peek(silo, "build:<sha256>")    # miss -> PENDING, bound to key
if p.state == PENDING:
    done = p.then(lambda v: v.upper())           # runs inside drain()
    p.resolve_commit('{"status":"ok"}')          # resolve + silo_set under the key
    drain()
silo.peek("build:<sha256>")                      # ('{"status":"ok"}', 0)
```

Handler return values become the dependent promise's value; raising rejects it
with `str(exc)`; returning a `Promise` adopts it. Same single-threaded rule as
the C library. `tests/test_q_promises_binding.py` runs one suite against both.

## Files

| File | Purpose |
|------|---------|
| `qpromise.h` / `qpromise.c` | Public API + implementation |
| `Q_promises.h` | Compat redirect |
| `test_qpromise.c` | Deterministic suite |
| `Q_promises.py` / `Q_promises.pyx` | Python bindings (ctypes / Cython) |
| `Promises.c` | Demo: peek → pending → commit → then |
| `Makefile` | `shared`, `test`, `test-asan`, `demo` |
