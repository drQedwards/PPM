/**
 * Promises.c — demo of retrieve → compute → pending → resolve → continuation
 * → PMLL memory update. Not the old Known/Unknown chain walker.
 */
#define _POSIX_C_SOURCE 200809L
#include "qpromise.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static qpromise_t *on_done(const char *value, void *user,
                           char **out_value, char **out_error)
{
    (void)user; (void)out_error;
    printf("continuation: %s\n", value ? value : "(null)");
    if (out_value) *out_value = value ? strdup(value) : NULL;
    return NULL;
}

int main(void)
{
    memory_silo_t *silo = init_silo(8);
    qpromise_t *p, *c;
    const char *v = NULL;
    int idx = -1;

    if (!silo) return 1;

    p = qpromise_from_peek(silo, "demo");
    if (!p) { free_silo(silo); return 1; }

    if (qpromise_state(p) == QPROMISE_PENDING) {
        printf("miss — computing...\n");
        c = qpromise_then(p, on_done, NULL);
        if (qpromise_resolve_commit(p, "demo-result", -1) != 0) {
            fprintf(stderr, "resolve_commit failed\n");
            qpromise_unref(c); qpromise_unref(p); free_silo(silo);
            return 1;
        }
        qpromise_drain();
        qpromise_unref(c);
    } else {
        printf("hit — %s\n", qpromise_value(p));
    }

    if (peek(silo, "demo", -1, &v, &idx))
        printf("silo[demo] = %s (index %d)\n", v, idx);

    qpromise_unref(p);
    free_silo(silo);
    return 0;
}
