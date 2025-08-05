#ifndef PMLL2_H
#define PMLL2_H

#include <stdlib.h>
#include <stdint.h>
#include <pthread.h>

/* ─────── Forward declaration ─────── */
typedef struct QMemNode QMemNode;

/* ─────── State-flag bit field ─────── */
typedef enum {
    PMLL_STATE_CONFLICT = 1u << 0,
    PMLL_STATE_SAT      = 1u << 1,
    PMLL_STATE_UNSAT    = 1u << 2
} pmll_state_flags_t;

/* ─────── A single assignment in the lattice ─────── */
typedef struct pmll_slot {
    QMemNode          *trace;     /* pointer back into Q_promises chain */
    struct pmll_slot  *next;      /* linked list (same lattice depth)   */
    int32_t            var;       /* DIMACS / internal variable id      */
    int8_t             value;     /* +1 = TRUE, -1 = FALSE              */
    uint32_t           depth;     /* recursion depth (0 == root)        */
} pmll_slot_t;

/* ─────── Whole lattice object ─────── */
typedef struct {
    pmll_slot_t  **layers;      /* array[depth] -> linked list head   */
    uint32_t       max_depth;
    uint32_t       state_flags;
#ifdef PMLL_THREAD_SAFE
    pthread_mutex_t mutex;
#endif
} pmll_lattice_t;

/* ─────── Public API ─────── */
pmll_lattice_t *pmll_init_lattice(uint32_t max_depth);
void            pmll_push_slot(pmll_lattice_t *lat,
                               uint32_t depth,
                               int32_t  var,
                               int8_t   value,
                               QMemNode *trace);
void            pmll_set_flag(pmll_lattice_t *lat, pmll_state_flags_t flag);
uint32_t        pmll_get_flags(const pmll_lattice_t *lat);
void            pmll_free_lattice(pmll_lattice_t *lat);

#endif /* PMLL2_H */
