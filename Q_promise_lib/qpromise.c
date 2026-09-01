/**
 * qpromise.c — PMLL Promise / Continuation Library
 *
 * Single-threaded. Continuations enqueue onto an internal job list and run
 * only inside qpromise_drain(). No threads are spawned.
 *
 * Q-promise = temporal/control-flow; PMLL = memory/state. Promises hold a
 * borrowed silo pointer + key/SAT metadata; they never copy the silo.
 */
#include "qpromise.h"

#include <stdlib.h>
#include <string.h>

#include "../PMLL.h"

/* ─── allocator (testable) ───────────────────────────────────────────────── */

static qpromise_malloc_fn g_malloc = NULL;
static qpromise_free_fn   g_free   = NULL;

static void *qp_malloc(size_t n)
{
    return g_malloc ? g_malloc(n) : malloc(n);
}

static void qp_free(void *p)
{
    if (!p) return;
    if (g_free) g_free(p);
    else free(p);
}

static char *qp_strdup(const char *s)
{
    size_t n;
    char *d;
    if (!s) return NULL;
    n = strlen(s) + 1;
    d = (char *)qp_malloc(n);
    if (d) memcpy(d, s, n);
    return d;
}

void qpromise_set_allocator(qpromise_malloc_fn m, qpromise_free_fn f)
{
    g_malloc = m;
    g_free = f;
}

/* ─── types ──────────────────────────────────────────────────────────────── */

typedef enum { QP_THEN = 1, QP_CATCH = 2, QP_FINALLY = 3 } qp_kind;

typedef struct qp_cont {
    qp_kind kind;
    qpromise_then_fn then_fn;
    qpromise_catch_fn catch_fn;
    qpromise_finally_fn finally_fn;
    void *user;
    qpromise_t *child;      /* ref held */
    int fired;
    struct qp_cont *next;
} qp_cont;

typedef struct qp_job {
    qpromise_t *promise;    /* ref held while queued */
    struct qp_job *next;
} qp_job;

struct qpromise {
    int refcount;
    qpromise_state_t state;
    char *value;
    char *error;
    qp_cont *conts;
    int settling;

    memory_silo_t *silo;    /* borrowed */
    char *memory_key;
    int sat_state_id;
    char *context;

    qpromise_t *following;  /* adopted upstream, ref held */
};

static qp_job *g_job_head = NULL;
static qp_job *g_job_tail = NULL;
static int g_draining = 0;

static void qp_drop_following(qpromise_t *p);
static int  qp_settle_resolved(qpromise_t *p, char *owned_value);
static int  qp_settle_rejected(qpromise_t *p, char *owned_error);
static void qp_fire_conts(qpromise_t *p);
static void qp_adopt_follow(qpromise_t *child, qpromise_t *returned);
static void qp_enqueue_fire(qpromise_t *p);

/* ─── lifecycle ──────────────────────────────────────────────────────────── */

static qpromise_t *qp_new(void)
{
    qpromise_t *p = (qpromise_t *)qp_malloc(sizeof(qpromise_t));
    if (!p) return NULL;
    memset(p, 0, sizeof(*p));
    p->refcount = 1;
    p->state = QPROMISE_PENDING;
    p->sat_state_id = -1;
    return p;
}

static void qp_free_conts(qp_cont *c)
{
    while (c) {
        qp_cont *n = c->next;
        if (c->child) qpromise_unref(c->child);
        qp_free(c);
        c = n;
    }
}

static void qp_destroy(qpromise_t *p)
{
    qp_free(p->value);
    qp_free(p->error);
    qp_free(p->memory_key);
    qp_free(p->context);
    qp_free_conts(p->conts);
    if (p->following) qpromise_unref(p->following);
    qp_free(p);
}

void qpromise_ref(qpromise_t *p)
{
    if (p) p->refcount++;
}

void qpromise_unref(qpromise_t *p)
{
    if (!p) return;
    if (--p->refcount <= 0)
        qp_destroy(p);
}

qpromise_t *qpromise_create(void)
{
    return qp_new();
}

qpromise_t *qpromise_resolved(const char *value)
{
    qpromise_t *p = qp_new();
    if (!p) return NULL;
    if (value) {
        p->value = qp_strdup(value);
        if (!p->value) { qpromise_unref(p); return NULL; }
    }
    p->state = QPROMISE_RESOLVED;
    return p;
}

qpromise_t *qpromise_rejected(const char *error)
{
    qpromise_t *p = qp_new();
    if (!p) return NULL;
    p->error = qp_strdup(error ? error : "rejected");
    if (!p->error) { qpromise_unref(p); return NULL; }
    p->state = QPROMISE_REJECTED;
    return p;
}

/* ─── job queue ──────────────────────────────────────────────────────────── */

static void qp_enqueue_fire(qpromise_t *p)
{
    qp_job *j;
    if (!p) return;
    j = (qp_job *)qp_malloc(sizeof(qp_job));
    if (!j) return; /* best-effort; caller still has settled state */
    qpromise_ref(p);
    j->promise = p;
    j->next = NULL;
    if (g_job_tail) g_job_tail->next = j;
    else g_job_head = j;
    g_job_tail = j;
}

size_t qpromise_jobs_pending(void)
{
    size_t n = 0;
    qp_job *j;
    for (j = g_job_head; j; j = j->next) n++;
    return n;
}

void qpromise_drain(void)
{
    if (g_draining) return;
    g_draining = 1;
    while (g_job_head) {
        qp_job *j = g_job_head;
        qpromise_t *p;
        g_job_head = j->next;
        if (!g_job_head) g_job_tail = NULL;
        p = j->promise;
        qp_free(j);
        qp_fire_conts(p);
        qpromise_unref(p);
    }
    g_draining = 0;
}

/* ─── settle ─────────────────────────────────────────────────────────────── */

static void qp_drop_following(qpromise_t *p)
{
    qpromise_t *f;
    if (!p || !p->following) return;
    f = p->following;
    p->following = NULL;
    qpromise_unref(f);
}

static int qp_settle_resolved(qpromise_t *p, char *owned_value)
{
    if (!p) { qp_free(owned_value); return -1; }
    if (p->state != QPROMISE_PENDING || p->settling) {
        qp_free(owned_value);
        return -1;
    }
    p->settling = 1;
    p->state = QPROMISE_RESOLVED;
    p->value = owned_value;
    qp_free(p->error);
    p->error = NULL;
    qp_drop_following(p);
    p->settling = 0;
    qp_enqueue_fire(p);
    return 0;
}

static int qp_settle_rejected(qpromise_t *p, char *owned_error)
{
    if (!p) { qp_free(owned_error); return -1; }
    if (p->state != QPROMISE_PENDING || p->settling) {
        qp_free(owned_error);
        return -1;
    }
    p->settling = 1;
    p->state = QPROMISE_REJECTED;
    if (!owned_error) owned_error = qp_strdup("rejected");
    p->error = owned_error;
    qp_free(p->value);
    p->value = NULL;
    qp_drop_following(p);
    p->settling = 0;
    qp_enqueue_fire(p);
    return 0;
}

int qpromise_resolve(qpromise_t *p, const char *value)
{
    char *copy = NULL;
    if (!p || p->state != QPROMISE_PENDING) return -1;
    if (value) {
        copy = qp_strdup(value);
        if (!copy) return -1;
    }
    return qp_settle_resolved(p, copy);
}

int qpromise_reject(qpromise_t *p, const char *error)
{
    char *copy;
    if (!p || p->state != QPROMISE_PENDING) return -1;
    copy = qp_strdup(error ? error : "rejected");
    if (!copy) return -1;
    return qp_settle_rejected(p, copy);
}

int qpromise_cancel(qpromise_t *p)
{
    if (!p || p->state != QPROMISE_PENDING || p->settling) return -1;
    p->settling = 1;
    p->state = QPROMISE_CANCELLED;
    qp_free(p->value); p->value = NULL;
    qp_free(p->error); p->error = NULL;
    qp_drop_following(p);
    p->settling = 0;
    qp_enqueue_fire(p);
    return 0;
}

qpromise_state_t qpromise_state(const qpromise_t *p)
{
    return p ? p->state : QPROMISE_REJECTED;
}

const char *qpromise_value(const qpromise_t *p)
{
    return (p && p->state == QPROMISE_RESOLVED) ? p->value : NULL;
}

const char *qpromise_error(const qpromise_t *p)
{
    return (p && p->state == QPROMISE_REJECTED) ? p->error : NULL;
}

/* ─── continuations ──────────────────────────────────────────────────────── */

static qp_cont *qp_cont_new(qp_kind kind, qpromise_t *child)
{
    qp_cont *c = (qp_cont *)qp_malloc(sizeof(qp_cont));
    if (!c) return NULL;
    memset(c, 0, sizeof(*c));
    c->kind = kind;
    c->child = child;
    if (child) qpromise_ref(child);
    return c;
}

static void qp_cont_append(qpromise_t *p, qp_cont *c)
{
    if (!p->conts) {
        p->conts = c;
        return;
    }
    {
        qp_cont *t = p->conts;
        while (t->next) t = t->next;
        t->next = c;
    }
}

qpromise_t *qpromise_then(qpromise_t *p, qpromise_then_fn fn, void *user)
{
    qpromise_t *child;
    qp_cont *c;
    if (!p || !fn) return NULL;
    child = qp_new();
    if (!child) return NULL;
    c = qp_cont_new(QP_THEN, child);
    if (!c) { qpromise_unref(child); return NULL; }
    c->then_fn = fn;
    c->user = user;
    qp_cont_append(p, c);
    if (p->state != QPROMISE_PENDING)
        qp_enqueue_fire(p);
    return child;
}

qpromise_t *qpromise_catch(qpromise_t *p, qpromise_catch_fn fn, void *user)
{
    qpromise_t *child;
    qp_cont *c;
    if (!p || !fn) return NULL;
    child = qp_new();
    if (!child) return NULL;
    c = qp_cont_new(QP_CATCH, child);
    if (!c) { qpromise_unref(child); return NULL; }
    c->catch_fn = fn;
    c->user = user;
    qp_cont_append(p, c);
    if (p->state != QPROMISE_PENDING)
        qp_enqueue_fire(p);
    return child;
}

qpromise_t *qpromise_finally(qpromise_t *p, qpromise_finally_fn fn, void *user)
{
    qpromise_t *child;
    qp_cont *c;
    if (!p || !fn) return NULL;
    child = qp_new();
    if (!child) return NULL;
    c = qp_cont_new(QP_FINALLY, child);
    if (!c) { qpromise_unref(child); return NULL; }
    c->finally_fn = fn;
    c->user = user;
    qp_cont_append(p, c);
    if (p->state != QPROMISE_PENDING)
        qp_enqueue_fire(p);
    return child;
}

/* ─── fire / adopt ───────────────────────────────────────────────────────── */

static void qp_pass_through(qpromise_t *child, const qpromise_t *parent)
{
    if (!child || child->state != QPROMISE_PENDING) return;
    if (parent->state == QPROMISE_RESOLVED) {
        char *v = parent->value ? qp_strdup(parent->value) : NULL;
        if (parent->value && !v) {
            (void)qp_settle_rejected(child, qp_strdup("oom"));
            return;
        }
        (void)qp_settle_resolved(child, v);
    } else if (parent->state == QPROMISE_REJECTED) {
        char *e = parent->error ? qp_strdup(parent->error) : qp_strdup("rejected");
        (void)qp_settle_rejected(child, e);
    } else if (parent->state == QPROMISE_CANCELLED) {
        (void)qpromise_cancel(child);
    }
}

static qpromise_t *qp_adopt_on_then(const char *value, void *user,
                                    char **out_value, char **out_error)
{
    (void)user;
    (void)out_error;
    if (out_value) *out_value = value ? qp_strdup(value) : NULL;
    return NULL;
}

static qpromise_t *qp_adopt_on_catch(const char *error, void *user,
                                     char **out_value, char **out_error)
{
    (void)user;
    (void)out_value;
    if (out_error) *out_error = qp_strdup(error ? error : "rejected");
    return NULL;
}

static void qp_adopt_follow(qpromise_t *child, qpromise_t *returned)
{
    qp_cont *c_ok, *c_err;
    if (!child || !returned) return;
    if (child->state != QPROMISE_PENDING) return;

    if (returned->state == QPROMISE_RESOLVED) {
        char *v = returned->value ? qp_strdup(returned->value) : NULL;
        (void)qp_settle_resolved(child, v);
        return;
    }
    if (returned->state == QPROMISE_REJECTED) {
        char *e = returned->error ? qp_strdup(returned->error)
                                  : qp_strdup("rejected");
        (void)qp_settle_rejected(child, e);
        return;
    }
    if (returned->state == QPROMISE_CANCELLED) {
        (void)qpromise_cancel(child);
        return;
    }

    if (child->following) qpromise_unref(child->following);
    qpromise_ref(returned);
    child->following = returned;

    c_ok = qp_cont_new(QP_THEN, child);
    c_err = qp_cont_new(QP_CATCH, child);
    if (!c_ok || !c_err) {
        if (c_ok) {
            if (c_ok->child) qpromise_unref(c_ok->child);
            qp_free(c_ok);
        }
        if (c_err) {
            if (c_err->child) qpromise_unref(c_err->child);
            qp_free(c_err);
        }
        (void)qp_settle_rejected(child, qp_strdup("oom adopting"));
        return;
    }
    c_ok->then_fn = qp_adopt_on_then;
    c_err->catch_fn = qp_adopt_on_catch;
    qp_cont_append(returned, c_ok);
    qp_cont_append(returned, c_err);
}

static void qp_apply_result(qpromise_t *child, qpromise_t *returned,
                            char *out_value, char *out_error)
{
    if (out_error) {
        qp_free(out_value);
        if (returned) qpromise_unref(returned);
        (void)qp_settle_rejected(child, out_error);
        return;
    }
    if (returned) {
        qp_free(out_value);
        qp_adopt_follow(child, returned);
        qpromise_unref(returned);
        return;
    }
    (void)qp_settle_resolved(child, out_value);
}

static void qp_fire_conts(qpromise_t *p)
{
    qp_cont *c;
    if (!p || p->state == QPROMISE_PENDING) return;

    for (c = p->conts; c; c = c->next) {
        char *out_v = NULL, *out_e = NULL;
        qpromise_t *ret = NULL;

        if (c->fired) continue;

        if (p->state == QPROMISE_CANCELLED) {
            c->fired = 1;
            if (c->kind == QP_FINALLY && c->finally_fn)
                c->finally_fn(c->user);
            if (c->child && c->child->state == QPROMISE_PENDING)
                (void)qpromise_cancel(c->child);
            continue;
        }

        if (c->kind == QP_THEN) {
            c->fired = 1;
            if (p->state == QPROMISE_RESOLVED) {
                ret = c->then_fn(p->value, c->user, &out_v, &out_e);
                qp_apply_result(c->child, ret, out_v, out_e);
            } else {
                qp_pass_through(c->child, p);
            }
        } else if (c->kind == QP_CATCH) {
            c->fired = 1;
            if (p->state == QPROMISE_REJECTED) {
                ret = c->catch_fn(p->error, c->user, &out_v, &out_e);
                qp_apply_result(c->child, ret, out_v, out_e);
            } else {
                qp_pass_through(c->child, p);
            }
        } else { /* FINALLY */
            c->fired = 1;
            if (c->finally_fn) c->finally_fn(c->user);
            qp_pass_through(c->child, p);
        }
    }
}

/* ─── PMLL integration ───────────────────────────────────────────────────── */

int qpromise_bind_pmll(qpromise_t *p, memory_silo_t *silo,
                       const char *memory_key, int sat_state_id,
                       const char *context)
{
    char *k = NULL, *ctx = NULL;
    if (!p || !silo) return -1;
    if (memory_key) {
        k = qp_strdup(memory_key);
        if (!k) return -1;
    }
    if (context) {
        ctx = qp_strdup(context);
        if (!ctx) { qp_free(k); return -1; }
    }
    qp_free(p->memory_key);
    qp_free(p->context);
    p->silo = silo;
    p->memory_key = k;
    p->context = ctx;
    p->sat_state_id = sat_state_id;
    return 0;
}

const char *qpromise_pmll_key(const qpromise_t *p)
{
    return p ? p->memory_key : NULL;
}

int qpromise_pmll_sat_id(const qpromise_t *p)
{
    return p ? p->sat_state_id : -1;
}

const char *qpromise_pmll_context(const qpromise_t *p)
{
    return p ? p->context : NULL;
}

memory_silo_t *qpromise_pmll_silo(const qpromise_t *p)
{
    return p ? p->silo : NULL;
}

qpromise_t *qpromise_from_peek(memory_silo_t *silo, const char *key)
{
    const char *val = NULL;
    int idx = -1;
    qpromise_t *p;

    if (!silo || !key) return NULL;

    if (peek(silo, key, -1, &val, &idx)) {
        p = qpromise_resolved(val);
        if (!p) return NULL;
        if (qpromise_bind_pmll(p, silo, key, -1, NULL) != 0) {
            /* still usable; binding is best-effort metadata */
        }
        return p;
    }

    p = qpromise_create();
    if (!p) return NULL;
    if (qpromise_bind_pmll(p, silo, key, -1, NULL) != 0) {
        qpromise_unref(p);
        return NULL;
    }
    return p;
}

qpromise_t *qpromise_from_peek_semantic(memory_silo_t *silo,
                                        const char *query, float min_sim)
{
    const char *val = NULL;
    int idx = -1;
    float sim = 0.0f;
    qpromise_t *p;
    const char *hit_key = NULL;

    if (!silo || !query) return NULL;

    if (peek_semantic(silo, query, min_sim, &val, &idx, &sim)) {
        if (idx >= 0 && idx < silo->size)
            hit_key = silo->slots[idx].key;
        p = qpromise_resolved(val);
        if (!p) return NULL;
        (void)qpromise_bind_pmll(p, silo, hit_key, -1, query);
        return p;
    }

    p = qpromise_create();
    if (!p) return NULL;
    if (qpromise_bind_pmll(p, silo, NULL, -1, query) != 0) {
        qpromise_unref(p);
        return NULL;
    }
    return p;
}

int qpromise_resolve_commit(qpromise_t *p, const char *value, int silo_index)
{
    int idx;
    const char *key;
    if (!p || p->state != QPROMISE_PENDING) return -1;
    if (!p->silo || !value) return -1;
    key = p->memory_key;
    idx = silo_set(p->silo, silo_index, key, value);
    if (idx < 0) return -1;
    return qpromise_resolve(p, value);
}
