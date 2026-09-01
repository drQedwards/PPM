/**
 * qpromise.h — PMLL Promise / Continuation Library (Q-promise)
 *
 * Temporal / control-flow layer for PMLL. Promises REFERENCE PMLL memory
 * (silo key, optional SAT id); they do not replace or duplicate the silo.
 *
 * Thread safety: SINGLE-THREADED. Callers must externally serialize access.
 * Continuations are deferred onto an internal job queue and run only when
 * qpromise_drain() is invoked (scheduler isolated from this API).
 *
 * Ownership: qpromise_create / qpromise_resolved / qpromise_rejected /
 * qpromise_then / qpromise_catch / qpromise_finally / qpromise_from_peek*
 * return a promise with refcount 1. Call qpromise_unref() when done.
 *
 * Breaking vs the QMemNode seed: the prototype was a linked "memory chain"
 * walker (q_mem_create_chain / q_then). That API is removed. Public symbols
 * are prefixed qpromise_*.
 */
#ifndef QPROMISE_H
#define QPROMISE_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stddef.h>
#include "../PMLL.h"

typedef enum {
    QPROMISE_PENDING   = 0,
    QPROMISE_RESOLVED  = 1,
    QPROMISE_REJECTED  = 2,
    QPROMISE_CANCELLED = 3
} qpromise_state_t;

typedef struct qpromise qpromise_t;

/**
 * Then / catch handlers.
 *
 * Return a non-NULL qpromise_t* to adopt that promise's eventual state
 * (continuation returning another promise). Caller transfers one ref.
 *
 * Otherwise return NULL and optionally set:
 *   *out_value — malloc'd string; dependent resolves with it (ownership
 *                transfers to the library). NULL => resolve with NULL.
 *   *out_error — malloc'd string; dependent rejects (wins over out_value).
 *
 * Handlers run at most once. Never invoked after CANCELLED (except
 * finally, which always runs for cleanup).
 */
typedef qpromise_t *(*qpromise_then_fn)(const char *value, void *user,
                                       char **out_value, char **out_error);
typedef qpromise_t *(*qpromise_catch_fn)(const char *error, void *user,
                                        char **out_value, char **out_error);
typedef void (*qpromise_finally_fn)(void *user);

typedef void *(*qpromise_malloc_fn)(size_t n);
typedef void  (*qpromise_free_fn)(void *p);
void qpromise_set_allocator(qpromise_malloc_fn m, qpromise_free_fn f);

/* Lifecycle ------------------------------------------------------------------ */
qpromise_t *qpromise_create(void);
qpromise_t *qpromise_resolved(const char *value);
qpromise_t *qpromise_rejected(const char *error);

void qpromise_ref(qpromise_t *p);
void qpromise_unref(qpromise_t *p);

/* Settle: 0 ok; -1 if not pending / args / alloc (no double-settle) --------- */
int qpromise_resolve(qpromise_t *p, const char *value);
int qpromise_reject(qpromise_t *p, const char *error);
int qpromise_cancel(qpromise_t *p);

/* Query ---------------------------------------------------------------------- */
qpromise_state_t qpromise_state(const qpromise_t *p);
const char *qpromise_value(const qpromise_t *p);
const char *qpromise_error(const qpromise_t *p);

/* Chaining: new promise ref=1, or NULL on OOM -------------------------------- */
qpromise_t *qpromise_then(qpromise_t *p, qpromise_then_fn fn, void *user);
qpromise_t *qpromise_catch(qpromise_t *p, qpromise_catch_fn fn, void *user);
qpromise_t *qpromise_finally(qpromise_t *p, qpromise_finally_fn fn, void *user);

/* Scheduler (isolated) ------------------------------------------------------- */
void qpromise_drain(void);
size_t qpromise_jobs_pending(void);

/* PMLL integration — references, never copies the silo ---------------------- */
int qpromise_bind_pmll(qpromise_t *p, memory_silo_t *silo,
                       const char *memory_key, int sat_state_id,
                       const char *context);

const char *qpromise_pmll_key(const qpromise_t *p);
int         qpromise_pmll_sat_id(const qpromise_t *p);
const char *qpromise_pmll_context(const qpromise_t *p);
memory_silo_t *qpromise_pmll_silo(const qpromise_t *p);

/**
 * Exact peek → promise. Hit: RESOLVED with copied content. Miss: PENDING
 * bound to key (caller computes, then qpromise_resolve_commit / resolve).
 */
qpromise_t *qpromise_from_peek(memory_silo_t *silo, const char *key);

/**
 * Semantic peek → promise. Hit: RESOLVED. Miss: PENDING with context=query.
 */
qpromise_t *qpromise_from_peek_semantic(memory_silo_t *silo,
                                        const char *query, float min_sim);

/**
 * Resolve + silo_set under the bound key (silo_index -1 = next free).
 * Pattern: promise → resolve → PMLL memory update.
 */
int qpromise_resolve_commit(qpromise_t *p, const char *value, int silo_index);

#ifdef __cplusplus
}
#endif

#endif /* QPROMISE_H */
