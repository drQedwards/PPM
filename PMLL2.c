#include "PMLL2.h"
#include <stdio.h>
#include <string.h>

/* ─────── Internal helpers ─────── */
#ifdef PMLL_THREAD_SAFE
#define LATTICE_LOCK(l)   pthread_mutex_lock(&(l)->mutex)
#define LATTICE_UNLOCK(l) pthread_mutex_unlock(&(l)->mutex)
#else
#define LATTICE_LOCK(l)
#define LATTICE_UNLOCK(l)
#endif

/* --------------------------------------------------------------------------
 * pmll_init_lattice
 * ------------------------------------------------------------------------ */
pmll_lattice_t *pmll_init_lattice(uint32_t max_depth)
{
    if (max_depth == 0) return NULL;

    pmll_lattice_t *lat = (pmll_lattice_t *)calloc(1, sizeof *lat);
    if (!lat) return NULL;

    lat->max_depth   = max_depth;
    lat->state_flags = 0;
    lat->layers      = (pmll_slot_t **)calloc(max_depth, sizeof(pmll_slot_t *));
    if (!lat->layers) { free(lat); return NULL; }

#ifdef PMLL_THREAD_SAFE
    if (pthread_mutex_init(&lat->mutex, NULL) != 0) {
        free(lat->layers); free(lat); return NULL;
    }
#endif
    return lat;
}

/* --------------------------------------------------------------------------
 * pmll_push_slot
 * ------------------------------------------------------------------------ */
void pmll_push_slot(pmll_lattice_t *lat,
                    uint32_t depth,
                    int32_t  var,
                    int8_t   value,
                    QMemNode *trace)
{
    if (!lat || depth >= lat->max_depth) return;

    LATTICE_LOCK(lat);

    pmll_slot_t *node = (pmll_slot_t *)malloc(sizeof *node);
    if (!node) { LATTICE_UNLOCK(lat); return; }

    node->trace = trace;
    node->var   = var;
    node->value = value;
    node->depth = depth;
    node->next  = lat->layers[depth];
    lat->layers[depth] = node;

    /* Simple example logic: value == 0 => conflict */
    if (value == 0)
        lat->state_flags |= PMLL_STATE_CONFLICT;

    LATTICE_UNLOCK(lat);
}

/* --------------------------------------------------------------------------
 * pmll_set_flag / pmll_get_flags
 * ------------------------------------------------------------------------ */
void pmll_set_flag(pmll_lattice_t *lat, pmll_state_flags_t flag)
{
    if (!lat) return;
    LATTICE_LOCK(lat);
    lat->state_flags |= flag;
    LATTICE_UNLOCK(lat);
}

uint32_t pmll_get_flags(const pmll_lattice_t *lat)
{
    return lat ? lat->state_flags : 0;
}

/* --------------------------------------------------------------------------
 * pmll_free_lattice
 * ------------------------------------------------------------------------ */
void pmll_free_lattice(pmll_lattice_t *lat)
{
    if (!lat) return;

    for (uint32_t d = 0; d < lat->max_depth; ++d) {
        pmll_slot_t *cur = lat->layers[d];
        while (cur) {
            pmll_slot_t *next = cur->next;
            free(cur);
            cur = next;
        }
    }
    free(lat->layers);

#ifdef PMLL_THREAD_SAFE
    pthread_mutex_destroy(&lat->mutex);
#endif
    free(lat);
}

/* --------------------------------------------------------------------------
 * Optional self-test (compile with -DPMLL2_TEST)
 * ------------------------------------------------------------------------ */
#ifdef PMLL2_TEST
#include <assert.h>
int main(void)
{
    pmll_lattice_t *lat = pmll_init_lattice(4);
    assert(lat);

    pmll_push_slot(lat, 0, 1, +1, NULL);
    pmll_push_slot(lat, 1, 2,  0, NULL);   /* sets CONFLICT */

    assert(pmll_get_flags(lat) & PMLL_STATE_CONFLICT);

    pmll_free_lattice(lat);
    puts("PMLL2 self-test OK");
    return 0;
}
#endif
