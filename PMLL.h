#ifndef PMLL_H
#define PMLL_H

#include <stddef.h>

/* Fixed embedding dimensionality for silo semantic vectors (hashing trick). */
#define PMLL_EMBED_DIM 32

/* Structure definitions */
typedef struct {
    int length;
    int *literals;
} clause_t;

/* One associative / semantic slot parallel to a tree index. */
typedef struct {
    char *key;          /* lookup key (malloc'd), may be NULL */
    char *content;      /* associative memory string (malloc'd) */
    float *embedding;   /* L2-normalized vector, length embed_dim */
    int resolved;       /* 1 once content has been committed */
} silo_slot_t;

typedef struct {
    int *tree;          /* integer tree array (size * 2), malloc/calloc owned */
    int size;           /* logical variable / slot capacity */
    silo_slot_t *slots; /* semantic layer: size entries, malloc owned */
    int embed_dim;      /* == PMLL_EMBED_DIM */
    int slot_count;     /* number of resolved semantic slots */
} memory_silo_t;

typedef struct {
    int num_vars;
    int num_clauses;
    clause_t *clauses;
    int *assignment;    /* -1 unassigned, 0 false, 1 true */
    memory_silo_t *silo;
    int flag;           /* 1 = solved / terminated (NOT an assignment value) */
} pml_t;

/* Function prototypes — silo / tree */
memory_silo_t *init_silo(int size);
void update_silo(memory_silo_t *silo, int var, int value, int depth);
void free_silo(memory_silo_t *silo);

/* Semantic store: write key/content + embedding at tree index (or next free). */
int silo_set(memory_silo_t *silo, int index, const char *key, const char *content);

/*
 * peek — dual-path non-destructive retrieval (mirrors MCP peek):
 *   1) Exact key match when key != NULL
 *   2) Else index lookup when index >= 0
 * Returns 1 on hit; *out_value points at silo-owned string (do not free);
 * *out_index receives the slot index. Miss => 0.
 */
int peek(memory_silo_t *silo, const char *key, int index,
         const char **out_value, int *out_index);

/*
 * peek_semantic — cosine similarity over embeddings.
 * On hit (best score >= min_sim), fills out_* like peek and returns 1.
 */
int peek_semantic(memory_silo_t *silo, const char *query, float min_sim,
                  const char **out_value, int *out_index, float *out_sim);

/* Lightweight text → embedding (feature hashing), L2-normalized into out[dim]. */
void silo_embed_text(const char *text, float *out, int dim);
float silo_cosine_similarity(const float *a, const float *b, int dim);

/* SAT stack bridge: boolean / 3SAT tokens → associative memory strings in silo */
int sat_bridge_literal(pml_t *pml, int lit, const char *assoc_meaning);
int sat_bridge_clause(pml_t *pml, int clause_idx, const char *assoc_meaning);
int sat_bridge_assignment_meanings(pml_t *pml);

/* Core PML / SAT refine loop */
int check_conflict(clause_t *clauses, int *assignment, int num_clauses, int num_vars);
void pml_refine(pml_t *pml_ptr, int recursion_level);
void pml_logic_loop(pml_t *pml_ptr, int max_depth);
void output_to_ppm(pml_t *pml_ptr, const char *filename);
pml_t *init_pml(int num_vars, int num_clauses, clause_t *clauses);
void free_pml(pml_t *pml);

#endif /* PMLL_H */
