/**
 * test_qpromise.c — deterministic suite for the PMLL Promise library.
 * No external services. Exits 0 on success.
 */
#define _POSIX_C_SOURCE 200809L
#include "qpromise.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int g_failures = 0;
static int g_tests = 0;

#define CHECK(cond, msg) do { \
    g_tests++; \
    if (!(cond)) { \
        fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, msg); \
        g_failures++; \
    } \
} while (0)

/* ─── alloc failure injection ────────────────────────────────────────────── */

static int g_fail_after = -1;
static int g_alloc_count = 0;
static void *counting_malloc(size_t n)
{
    g_alloc_count++;
    if (g_fail_after >= 0 && g_alloc_count > g_fail_after)
        return NULL;
    return malloc(n);
}

static void counting_free(void *p) { free(p); }

static void reset_alloc(void)
{
    g_fail_after = -1;
    g_alloc_count = 0;
    qpromise_set_allocator(NULL, NULL);
}

/* ─── handlers ───────────────────────────────────────────────────────────── */

static int g_then_calls = 0;
static int g_catch_calls = 0;
static int g_finally_calls = 0;

static qpromise_t *on_then_passthrough(const char *value, void *user,
                                       char **out_value, char **out_error)
{
    (void)user; (void)out_error;
    g_then_calls++;
    if (out_value) *out_value = value ? strdup(value) : NULL;
    return NULL;
}

static qpromise_t *on_then_append(const char *value, void *user,
                                  char **out_value, char **out_error)
{
    const char *suf = user ? (const char *)user : "";
    size_t n;
    char *buf;
    (void)out_error;
    g_then_calls++;
    n = (value ? strlen(value) : 0) + strlen(suf) + 1;
    buf = (char *)malloc(n);
    if (!buf) { if (out_error) *out_error = strdup("oom"); return NULL; }
    snprintf(buf, n, "%s%s", value ? value : "", suf);
    *out_value = buf;
    return NULL;
}

static qpromise_t *on_then_return_promise(const char *value, void *user,
                                          char **out_value, char **out_error)
{
    (void)out_value; (void)out_error; (void)user;
    g_then_calls++;
    return qpromise_resolved(value ? value : "inner");
}

static qpromise_t *on_then_return_pending(const char *value, void *user,
                                          char **out_value, char **out_error)
{
    qpromise_t **slot = (qpromise_t **)user;
    (void)value; (void)out_value; (void)out_error;
    g_then_calls++;
    *slot = qpromise_create();
    qpromise_ref(*slot); /* keep for test */
    return *slot;
}

static qpromise_t *on_catch_recover(const char *error, void *user,
                                    char **out_value, char **out_error)
{
    (void)error; (void)out_error;
    g_catch_calls++;
    if (out_value) *out_value = strdup(user ? (const char *)user : "recovered");
    return NULL;
}

static void on_finally(void *user)
{
    int *p = (int *)user;
    g_finally_calls++;
    if (p) (*p)++;
}

static void reset_counts(void)
{
    g_then_calls = g_catch_calls = g_finally_calls = 0;
}

/* ─── tests ──────────────────────────────────────────────────────────────── */

static void test_pending_resolve_reject(void)
{
    qpromise_t *p = qpromise_create();
    CHECK(p != NULL, "create");
    CHECK(qpromise_state(p) == QPROMISE_PENDING, "pending");
    CHECK(qpromise_resolve(p, "ok") == 0, "resolve");
    CHECK(qpromise_state(p) == QPROMISE_RESOLVED, "resolved");
    CHECK(strcmp(qpromise_value(p), "ok") == 0, "value");
    CHECK(qpromise_resolve(p, "again") != 0, "no double resolve");
    CHECK(qpromise_reject(p, "nope") != 0, "no reject after resolve");
    qpromise_unref(p);

    p = qpromise_create();
    CHECK(qpromise_reject(p, "err") == 0, "reject");
    CHECK(qpromise_state(p) == QPROMISE_REJECTED, "rejected");
    CHECK(strcmp(qpromise_error(p), "err") == 0, "error");
    CHECK(qpromise_reject(p, "again") != 0, "no double reject");
    qpromise_unref(p);
}

static void test_then_and_already_resolved(void)
{
    qpromise_t *p, *c;
    reset_counts();

    p = qpromise_create();
    c = qpromise_then(p, on_then_passthrough, NULL);
    CHECK(c != NULL, "then child");
    CHECK(qpromise_resolve(p, "A") == 0, "resolve A");
    CHECK(g_then_calls == 0, "deferred before drain");
    qpromise_drain();
    CHECK(g_then_calls == 1, "then fired once");
    CHECK(qpromise_state(c) == QPROMISE_RESOLVED, "child resolved");
    CHECK(strcmp(qpromise_value(c), "A") == 0, "child value");
    qpromise_drain();
    CHECK(g_then_calls == 1, "then not re-fired");
    qpromise_unref(c);
    qpromise_unref(p);

    /* already-resolved then */
    reset_counts();
    p = qpromise_resolved("ready");
    c = qpromise_then(p, on_then_passthrough, NULL);
    qpromise_drain();
    CHECK(g_then_calls == 1, "already-resolved then");
    CHECK(strcmp(qpromise_value(c), "ready") == 0, "already value");
    qpromise_unref(c);
    qpromise_unref(p);
}

static void test_rejection_propagation_and_recovery(void)
{
    qpromise_t *p, *t, *r;
    reset_counts();
    p = qpromise_create();
    t = qpromise_then(p, on_then_passthrough, NULL);
    r = qpromise_catch(t, on_catch_recover, (void *)"fixed");
    CHECK(qpromise_reject(p, "boom") == 0, "reject boom");
    qpromise_drain();
    CHECK(g_then_calls == 0, "then skipped on reject");
    CHECK(g_catch_calls == 1, "catch fired");
    CHECK(qpromise_state(t) == QPROMISE_REJECTED, "then child rejected");
    CHECK(qpromise_state(r) == QPROMISE_RESOLVED, "recovered");
    CHECK(strcmp(qpromise_value(r), "fixed") == 0, "recovered value");
    qpromise_unref(r); qpromise_unref(t); qpromise_unref(p);
}

static void test_chained_then(void)
{
    qpromise_t *p, *a, *b;
    reset_counts();
    p = qpromise_create();
    a = qpromise_then(p, on_then_append, (void *)"-1");
    b = qpromise_then(a, on_then_append, (void *)"-2");
    CHECK(qpromise_resolve(p, "x") == 0, "resolve x");
    qpromise_drain();
    CHECK(g_then_calls == 2, "two thens");
    CHECK(strcmp(qpromise_value(b), "x-1-2") == 0, "chained value");
    qpromise_unref(b); qpromise_unref(a); qpromise_unref(p);
}

static void test_then_return_promise(void)
{
    qpromise_t *p, *c, *inner = NULL;
    reset_counts();

    /* return already-resolved promise */
    p = qpromise_resolved("outer");
    c = qpromise_then(p, on_then_return_promise, NULL);
    qpromise_drain();
    CHECK(g_then_calls == 1, "return-promise then");
    CHECK(qpromise_state(c) == QPROMISE_RESOLVED, "adopted resolved");
    CHECK(strcmp(qpromise_value(c), "outer") == 0, "adopted value");
    qpromise_unref(c); qpromise_unref(p);

    /* return pending, then settle later */
    reset_counts();
    p = qpromise_resolved("go");
    c = qpromise_then(p, on_then_return_pending, &inner);
    qpromise_drain();
    CHECK(g_then_calls == 1, "pending return then");
    CHECK(qpromise_state(c) == QPROMISE_PENDING, "child still pending");
    CHECK(inner != NULL, "inner created");
    CHECK(qpromise_resolve(inner, "late") == 0, "resolve inner");
    qpromise_drain();
    CHECK(qpromise_state(c) == QPROMISE_RESOLVED, "adopted late");
    CHECK(strcmp(qpromise_value(c), "late") == 0, "late value");
    qpromise_unref(inner);
    qpromise_unref(c); qpromise_unref(p);
}

static void test_multiple_continuations(void)
{
    qpromise_t *p, *a, *b, *c;
    reset_counts();
    p = qpromise_create();
    a = qpromise_then(p, on_then_passthrough, NULL);
    b = qpromise_then(p, on_then_passthrough, NULL);
    c = qpromise_then(p, on_then_passthrough, NULL);
    CHECK(qpromise_resolve(p, "multi") == 0, "resolve multi");
    qpromise_drain();
    CHECK(g_then_calls == 3, "three continuations");
    CHECK(strcmp(qpromise_value(a), "multi") == 0, "a");
    CHECK(strcmp(qpromise_value(b), "multi") == 0, "b");
    CHECK(strcmp(qpromise_value(c), "multi") == 0, "c");
    qpromise_unref(a); qpromise_unref(b); qpromise_unref(c); qpromise_unref(p);
}

static void test_cancel_and_finally(void)
{
    qpromise_t *p, *t, *f;
    int fin = 0;
    reset_counts();
    p = qpromise_create();
    t = qpromise_then(p, on_then_passthrough, NULL);
    f = qpromise_finally(p, on_finally, &fin);
    CHECK(qpromise_cancel(p) == 0, "cancel");
    qpromise_drain();
    CHECK(g_then_calls == 0, "then not after cancel");
    CHECK(g_finally_calls == 1, "finally after cancel");
    CHECK(fin == 1, "finally user");
    CHECK(qpromise_state(t) == QPROMISE_CANCELLED, "then child cancelled");
    CHECK(qpromise_state(f) == QPROMISE_CANCELLED, "finally child cancelled");
    CHECK(qpromise_resolve(p, "x") != 0, "no resolve after cancel");
    qpromise_unref(f); qpromise_unref(t); qpromise_unref(p);
}

static void test_cleanup_unref(void)
{
    qpromise_t *p = qpromise_resolved("z");
    qpromise_ref(p);
    qpromise_unref(p);
    qpromise_unref(p); /* should free without crash */
    CHECK(1, "unref cleanup");
}

static void test_alloc_failure(void)
{
    qpromise_t *p;
    reset_alloc();
    qpromise_set_allocator(counting_malloc, counting_free);
    g_fail_after = 0; /* first qp_malloc fails */
    g_alloc_count = 0;
    p = qpromise_create();
    CHECK(p == NULL, "create OOM");
    reset_alloc();
}

static void test_pmll_exact_and_commit(void)
{
    memory_silo_t *silo = init_silo(8);
    qpromise_t *p, *miss, *child;
    const char *got = NULL;
    int idx = -1;

    CHECK(silo != NULL, "init_silo");
    CHECK(silo_set(silo, 0, "alpha", "content-A") == 0, "silo_set alpha");

    /* exact hit → immediate resolve */
    p = qpromise_from_peek(silo, "alpha");
    CHECK(p != NULL, "from_peek hit");
    CHECK(qpromise_state(p) == QPROMISE_RESOLVED, "peek hit resolved");
    CHECK(strcmp(qpromise_value(p), "content-A") == 0, "peek value");
    CHECK(strcmp(qpromise_pmll_key(p), "alpha") == 0, "bound key");
    qpromise_unref(p);

    /* miss → pending, then commit */
    reset_counts();
    miss = qpromise_from_peek(silo, "beta");
    CHECK(miss != NULL, "from_peek miss");
    CHECK(qpromise_state(miss) == QPROMISE_PENDING, "miss pending");
    child = qpromise_then(miss, on_then_passthrough, NULL);
    CHECK(qpromise_resolve_commit(miss, "content-B", -1) == 0, "resolve_commit");
    qpromise_drain();
    CHECK(g_then_calls == 1, "commit fired then");
    CHECK(peek(silo, "beta", -1, &got, &idx) == 1, "silo has beta");
    CHECK(got && strcmp(got, "content-B") == 0, "committed content");
    CHECK(strcmp(qpromise_value(child), "content-B") == 0, "child after commit");
    qpromise_unref(child); qpromise_unref(miss);
    free_silo(silo);
}

static void test_pmll_semantic(void)
{
    memory_silo_t *silo = init_silo(8);
    qpromise_t *hit, *miss;
    CHECK(silo_set(silo, 0, "doc", "disjunction complementary polarity tokens") >= 0,
          "seed semantic");
    hit = qpromise_from_peek_semantic(silo, "complementary polarity", 0.1f);
    CHECK(hit != NULL, "semantic hit ptr");
    CHECK(qpromise_state(hit) == QPROMISE_RESOLVED, "semantic hit resolved");
    qpromise_unref(hit);

    miss = qpromise_from_peek_semantic(silo, "zzzz-unrelated-qqq", 0.99f);
    CHECK(miss != NULL, "semantic miss ptr");
    CHECK(qpromise_state(miss) == QPROMISE_PENDING, "semantic miss pending");
    CHECK(qpromise_pmll_context(miss) != NULL, "context=query");
    qpromise_unref(miss);
    free_silo(silo);
}

static void test_lookup_to_compute_loop(void)
{
    /* Explicit retrieve → compute → pending → resolve → continuation → memory */
    memory_silo_t *silo = init_silo(4);
    qpromise_t *p, *done;
    const char *v = NULL;
    int idx = -1;
    int fin = 0;

    p = qpromise_from_peek(silo, "work");
    CHECK(qpromise_state(p) == QPROMISE_PENDING, "loop start pending");
    done = qpromise_then(p, on_then_append, (void *)"-done");
    {
        qpromise_t *fin_p = qpromise_finally(done, on_finally, &fin);
        CHECK(fin_p != NULL, "finally attach");

        /* "compute" */
        CHECK(qpromise_resolve_commit(p, "result", -1) == 0, "loop commit");
        qpromise_drain();
        CHECK(strcmp(qpromise_value(done), "result-done") == 0, "loop cont");
        CHECK(peek(silo, "work", -1, &v, &idx) == 1, "loop memory");
        CHECK(fin == 1, "loop finally");

        /* second retrieve hits memory */
        {
            qpromise_t *again = qpromise_from_peek(silo, "work");
            CHECK(qpromise_state(again) == QPROMISE_RESOLVED, "loop retrieve hit");
            CHECK(strcmp(qpromise_value(again), "result") == 0, "loop cached");
            qpromise_unref(again);
        }
        qpromise_unref(fin_p);
    }
    qpromise_unref(done); qpromise_unref(p);
    free_silo(silo);
}

int main(void)
{
    test_pending_resolve_reject();
    test_then_and_already_resolved();
    test_rejection_propagation_and_recovery();
    test_chained_then();
    test_then_return_promise();
    test_multiple_continuations();
    test_cancel_and_finally();
    test_cleanup_unref();
    test_alloc_failure();
    test_pmll_exact_and_commit();
    test_pmll_semantic();
    test_lookup_to_compute_loop();

    /* drain any leftover */
    qpromise_drain();

    printf("qpromise tests: %d checks, %d failures\n", g_tests, g_failures);
    return g_failures ? 1 : 0;
}
