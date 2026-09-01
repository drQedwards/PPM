#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include "PMLL.h"

/* ─── helpers ─────────────────────────────────────────────────────────────── */

static char *pml_strdup(const char *s)
{
    size_t n;
    char *d;
    if (!s) return NULL;
    n = strlen(s) + 1;
    d = (char *)malloc(n);
    if (d) memcpy(d, s, n);
    return d;
}

static int tree_capacity(const memory_silo_t *silo)
{
    return silo->size * 2;
}

static int max_prop_depth(int size)
{
    if (size <= 1) return 1;
    return (int)log2((double)size);
}

/* Forward prop down the integer tree (children only — no cycle with back).
 * Tree uses parent=var/2; children of 0 are 1 and 2; else 2*var, 2*var+1.
 * Guard left/right > var so root (0) cannot recurse into itself via 2*0. */
static void propagate_forward(memory_silo_t *silo, int var, int value, int depth, int max_d)
{
    int left, right, cap;
    if (depth >= max_d) return;
    cap = tree_capacity(silo);
    if (var == 0) {
        left = 1;
        right = 2;
    } else {
        left = 2 * var;
        right = 2 * var + 1;
    }
    if (left < cap && left > var) {
        silo->tree[left] = value;
        propagate_forward(silo, left, value, depth + 1, max_d);
    }
    if (right < cap && right > var) {
        silo->tree[right] = value;
        propagate_forward(silo, right, value, depth + 1, max_d);
    }
}

/* Backward prop up toward root via parent = var/2. */
static void propagate_backward(memory_silo_t *silo, int var, int value, int depth, int max_d)
{
    if (var <= 0 || depth >= max_d || var >= tree_capacity(silo)) return;
    silo->tree[var] = value;
    propagate_backward(silo, var / 2, value, depth + 1, max_d);
}

/* ─── embeddings (feature hashing, no external deps) ─────────────────────── */

void silo_embed_text(const char *text, float *out, int dim)
{
    const char *p;
    char tok[64];
    int ti, i;
    float norm;

    if (!out || dim <= 0) return;
    memset(out, 0, (size_t)dim * sizeof(float));
    if (!text) return;

    p = text;
    while (*p) {
        while (*p && !isalnum((unsigned char)*p) && *p != '_' && *p != '-')
            p++;
        ti = 0;
        while (*p && (isalnum((unsigned char)*p) || *p == '_' || *p == '-') && ti < 63) {
            tok[ti++] = (char)tolower((unsigned char)*p++);
        }
        tok[ti] = '\0';
        if (ti > 1) {
            /* djb2-ish hash → bucket; signed contribution for diversity */
            unsigned long h = 5381;
            for (i = 0; i < ti; i++)
                h = ((h << 5) + h) + (unsigned char)tok[i];
            i = (int)(h % (unsigned)dim);
            out[i] += 1.0f;
            out[(int)((h >> 8) % (unsigned)dim)] += 0.5f;
        }
    }

    norm = 0.0f;
    for (i = 0; i < dim; i++)
        norm += out[i] * out[i];
    norm = sqrtf(norm);
    if (norm > 1e-10f) {
        for (i = 0; i < dim; i++)
            out[i] /= norm;
    }
}

float silo_cosine_similarity(const float *a, const float *b, int dim)
{
    float dot = 0.0f, na = 0.0f, nb = 0.0f;
    int i;
    if (!a || !b || dim <= 0) return 0.0f;
    for (i = 0; i < dim; i++) {
        dot += a[i] * b[i];
        na += a[i] * a[i];
        nb += b[i] * b[i];
    }
    na = sqrtf(na);
    nb = sqrtf(nb);
    if (na < 1e-10f || nb < 1e-10f) return 0.0f;
    return dot / (na * nb);
}

/* ─── silo lifecycle ─────────────────────────────────────────────────────── */

memory_silo_t *init_silo(int size)
{
    memory_silo_t *silo;
    int i;

    if (size <= 0) return NULL;
    silo = (memory_silo_t *)malloc(sizeof(memory_silo_t));
    if (!silo) return NULL;

    silo->size = size;
    silo->embed_dim = PMLL_EMBED_DIM;
    silo->slot_count = 0;
    silo->tree = (int *)calloc((size_t)size * 2, sizeof(int));
    silo->slots = (silo_slot_t *)calloc((size_t)size, sizeof(silo_slot_t));
    if (!silo->tree || !silo->slots) {
        free(silo->tree);
        free(silo->slots);
        free(silo);
        return NULL;
    }
    for (i = 0; i < size; i++) {
        silo->slots[i].key = NULL;
        silo->slots[i].content = NULL;
        silo->slots[i].embedding = NULL;
        silo->slots[i].resolved = 0;
    }
    return silo;
}

void free_silo(memory_silo_t *silo)
{
    int i;
    if (!silo) return;
    if (silo->slots) {
        for (i = 0; i < silo->size; i++) {
            free(silo->slots[i].key);
            free(silo->slots[i].content);
            free(silo->slots[i].embedding);
        }
        free(silo->slots);
    }
    free(silo->tree);
    free(silo);
}

/* Update memory silo with recursive back + forward cache on the integer tree */
void update_silo(memory_silo_t *silo, int var, int value, int depth)
{
    int max_d;
    if (!silo || var < 0 || var >= tree_capacity(silo)) return;

    silo->tree[var] = value;
    max_d = max_prop_depth(silo->size);
    if (depth >= max_d) return;

    /* Backwards: parent chain */
    if (var > 0)
        propagate_backward(silo, var / 2, value, depth + 1, max_d);
    /* Forwards: children subtree */
    propagate_forward(silo, var, value, depth, max_d);
}

int silo_set(memory_silo_t *silo, int index, const char *key, const char *content)
{
    silo_slot_t *slot;
    int idx = index;

    if (!silo || !content) return -1;
    if (idx < 0) {
        /* allocate next free resolved slot index */
        for (idx = 0; idx < silo->size; idx++) {
            if (!silo->slots[idx].resolved)
                break;
        }
    }
    if (idx < 0 || idx >= silo->size) return -1;

    slot = &silo->slots[idx];
    free(slot->key);
    free(slot->content);
    free(slot->embedding);

    slot->key = key ? pml_strdup(key) : NULL;
    slot->content = pml_strdup(content);
    slot->embedding = (float *)calloc((size_t)silo->embed_dim, sizeof(float));
    if (!slot->content || !slot->embedding) {
        free(slot->key); slot->key = NULL;
        free(slot->content); slot->content = NULL;
        free(slot->embedding); slot->embedding = NULL;
        slot->resolved = 0;
        return -1;
    }
    silo_embed_text(content, slot->embedding, silo->embed_dim);
    if (!slot->resolved) {
        slot->resolved = 1;
        silo->slot_count++;
    }
    /* Mirror into integer tree as "present" marker via existing prop path */
    update_silo(silo, idx, 1, 0);
    return idx;
}

int peek(memory_silo_t *silo, const char *key, int index,
         const char **out_value, int *out_index)
{
    int i;
    if (!silo) return 0;

    /* Path 1: exact key */
    if (key) {
        for (i = 0; i < silo->size; i++) {
            if (silo->slots[i].resolved && silo->slots[i].key &&
                strcmp(silo->slots[i].key, key) == 0) {
                if (out_value) *out_value = silo->slots[i].content;
                if (out_index) *out_index = i;
                return 1;
            }
        }
        return 0;
    }

    /* Path 2: index */
    if (index >= 0 && index < silo->size && silo->slots[index].resolved) {
        if (out_value) *out_value = silo->slots[index].content;
        if (out_index) *out_index = index;
        return 1;
    }
    return 0;
}

int peek_semantic(memory_silo_t *silo, const char *query, float min_sim,
                  const char **out_value, int *out_index, float *out_sim)
{
    float qvec[PMLL_EMBED_DIM];
    float best = -1.0f, s;
    int best_i = -1, i, dim;

    if (!silo || !query) return 0;
    /* Clamp so stack qvec[PMLL_EMBED_DIM] is never overrun */
    dim = silo->embed_dim;
    if (dim > PMLL_EMBED_DIM) dim = PMLL_EMBED_DIM;
    if (dim <= 0) return 0;
    silo_embed_text(query, qvec, dim);

    for (i = 0; i < silo->size; i++) {
        if (!silo->slots[i].resolved || !silo->slots[i].embedding)
            continue;
        s = silo_cosine_similarity(qvec, silo->slots[i].embedding, dim);
        if (s > best) {
            best = s;
            best_i = i;
        }
    }

    if (best_i < 0 || best < min_sim) return 0;
    if (out_value) *out_value = silo->slots[best_i].content;
    if (out_index) *out_index = best_i;
    if (out_sim) *out_sim = best;
    return 1;
}

/* ─── SAT stack bridge ───────────────────────────────────────────────────── */

int sat_bridge_literal(pml_t *pml, int lit, const char *assoc_meaning)
{
    char key[64];
    char buf[512];
    int var, idx;
    const char *existing = NULL;
    int existing_idx = -1;
    if (!pml || !pml->silo || lit == 0) return -1;

    var = abs(lit) - 1;
    snprintf(key, sizeof(key), "lit:%+d", lit);
    if (assoc_meaning && assoc_meaning[0])
        snprintf(buf, sizeof(buf), "LIT %s x%d=%s | %s",
                 lit > 0 ? "POS" : "NEG", var + 1,
                 lit > 0 ? "true" : "false", assoc_meaning);
    else
        snprintf(buf, sizeof(buf), "LIT %s x%d | boolean-logic-level literal token",
                 lit > 0 ? "POS" : "NEG", var + 1);

    /* Prefer updating an existing key; else next free slot (do not clobber clauses). */
    if (peek(pml->silo, key, -1, &existing, &existing_idx))
        idx = existing_idx;
    else
        idx = -1;
    return silo_set(pml->silo, idx, key, buf);
}

int sat_bridge_clause(pml_t *pml, int clause_idx, const char *assoc_meaning)
{
    char key[64];
    char buf[1024];
    int n, i, pos, lit;
    clause_t *c;

    if (!pml || !pml->silo || clause_idx < 0 || clause_idx >= pml->num_clauses)
        return -1;
    c = &pml->clauses[clause_idx];

    snprintf(key, sizeof(key), "clause:%d", clause_idx);
    pos = snprintf(buf, sizeof(buf), "3SAT clause[%d] tokens:", clause_idx);
    for (i = 0; i < c->length && pos < (int)sizeof(buf) - 32; i++) {
        lit = c->literals[i];
        pos += snprintf(buf + pos, sizeof(buf) - (size_t)pos, " %+d", lit);
    }
    if (assoc_meaning && assoc_meaning[0] && pos < (int)sizeof(buf) - 4)
        snprintf(buf + pos, sizeof(buf) - (size_t)pos, " | meaning: %s", assoc_meaning);
    else if (pos < (int)sizeof(buf) - 48)
        snprintf(buf + pos, sizeof(buf) - (size_t)pos,
                 " | associative memory string from boolean-logic-level literals");

    /* Keep stable key; reuse slot on re-bridge, else next free. */
    {
        const char *ex = NULL;
        int ex_i = -1;
        if (peek(pml->silo, key, -1, &ex, &ex_i))
            n = ex_i;
        else
            n = -1;
    }
    return silo_set(pml->silo, n, key, buf);
}

int sat_bridge_assignment_meanings(pml_t *pml)
{
    int i, n = 0, idx;
    char key[64], buf[128];
    const char *ex;
    int ex_i;
    if (!pml || !pml->silo) return 0;

    for (i = 0; i < pml->num_vars; i++) {
        if (pml->assignment[i] == -1) continue;
        snprintf(key, sizeof(key), "assign:x%d", i + 1);
        snprintf(buf, sizeof(buf), "x%d=%s (SAT assignment → associative memory)",
                 i + 1, pml->assignment[i] == 1 ? "true" : "false");
        ex = NULL; ex_i = -1;
        idx = peek(pml->silo, key, -1, &ex, &ex_i) ? ex_i : -1;
        if (silo_set(pml->silo, idx, key, buf) >= 0)
            n++;
    }
    return n;
}

/* ─── conflict / refine / loop ───────────────────────────────────────────── */

int check_conflict(clause_t *clauses, int *assignment, int num_clauses, int num_vars)
{
    for (int i = 0; i < num_clauses; i++) {
        int satisfied = 0;
        int undecided = 0;
        for (int j = 0; j < clauses[i].length; j++) {
            int lit = clauses[i].literals[j];
            int var = abs(lit) - 1;
            if (var >= num_vars) continue;
            /* -1 = unassigned: not falsified; clause may still be satisfiable */
            if (assignment[var] == -1) { undecided = 1; continue; }
            if (assignment[var] == (lit > 0)) { satisfied = 1; break; }
        }
        /* Conflict only when every literal is assigned and false */
        if (!satisfied && !undecided) return 1;
    }
    return 0;
}

void pml_refine(pml_t *pml_ptr, int recursion_level)
{
    int n = pml_ptr->num_vars;
    clause_t *clauses = pml_ptr->clauses;
    int *assignment = pml_ptr->assignment;
    memory_silo_t *silo = pml_ptr->silo;

    /* Unit Propagation */
    for (int i = 0; i < pml_ptr->num_clauses; i++) {
        if (clauses[i].length == 1 && recursion_level == 0) {
            int lit = clauses[i].literals[0];
            int var = abs(lit) - 1;
            if (var < n && assignment[var] == -1) {
                assignment[var] = (lit > 0) ? 1 : 0;
                update_silo(silo, var, assignment[var], 0);
            }
        }
    }

    int unassigned = -1;
    for (int i = 0; i < n; i++) {
        if (assignment[i] == -1) {
            unassigned = i;
            break;
        }
    }
    if (unassigned == -1) {
        /* All variables assigned — set solved flag (distinct from assignment values) */
        pml_ptr->flag = 1;
        sat_bridge_assignment_meanings(pml_ptr);
        return;
    }

    assignment[unassigned] = 0;
    if (check_conflict(clauses, assignment, pml_ptr->num_clauses, n)) {
        assignment[unassigned] = 1;
        if (check_conflict(clauses, assignment, pml_ptr->num_clauses, n)) {
            assignment[unassigned] = -1;
            update_silo(silo, unassigned, -1, 0);
            if (recursion_level < max_prop_depth(n)) {
                pml_refine(pml_ptr, recursion_level + 1); /* Ouroboros recursion */
            }
            return;
        }
    }
    update_silo(silo, unassigned, assignment[unassigned], 0);
}

void pml_logic_loop(pml_t *pml_ptr, int max_depth)
{
    int max_steps = pml_ptr->num_vars * pml_ptr->num_vars +
                    2 * pml_ptr->num_vars * (int)log2(pml_ptr->num_vars > 1 ? pml_ptr->num_vars : 2) +
                    pml_ptr->num_vars; /* phi(n) */
    int steps = 0;

    while (steps < max_steps) {
        if (pml_ptr->flag == 1) break;
        pml_refine(pml_ptr, 0);
        steps++;
        if (max_steps >= 10 && steps % (max_steps / 10) == 0 && max_depth > 0) {
            pml_logic_loop(pml_ptr, max_depth - 1);
        }
    }

    if (steps >= max_steps && pml_ptr->flag != 1) {
        printf("Max steps reached, possible unsatisfiable.\n");
        pml_ptr->flag = 1;
    }
}

/* PPM output: grayscale image of assignments (255=true, 0=false, 128=unassigned) */
void output_to_ppm(pml_t *pml_ptr, const char *filename)
{
    FILE *fp = fopen(filename, "wb");
    if (!fp) return;
    fprintf(fp, "P5\n%d %d\n255\n", pml_ptr->num_vars, 1);
    for (int i = 0; i < pml_ptr->num_vars; i++) {
        unsigned char value = (pml_ptr->assignment[i] == 1) ? 255 :
                            (pml_ptr->assignment[i] == 0) ? 0 : 128;
        fwrite(&value, sizeof(unsigned char), 1, fp);
    }
    fclose(fp);
}

/*
 * Initialize PMLL.
 * REQUIRED: every assignment[i] starts at -1 (unassigned). calloc(0) falsely
 * marked all vars false, so pml_refine immediately saw "no unassigned", set
 * flag=1, and output_to_ppm collapsed to all-black. flag is a separate
 * solved/terminated indicator and starts at 0.
 */
pml_t *init_pml(int num_vars, int num_clauses, clause_t *clauses)
{
    pml_t *pml = (pml_t *)malloc(sizeof(pml_t));
    if (!pml) return NULL;

    pml->num_vars = num_vars;
    pml->num_clauses = num_clauses;
    pml->clauses = clauses;
    pml->assignment = (int *)malloc((size_t)num_vars * sizeof(int));
    if (!pml->assignment) {
        free(pml);
        return NULL;
    }
    for (int i = 0; i < num_vars; i++)
        pml->assignment[i] = -1; /* unassigned — never sticky 0/1 from calloc */
    /* Tree covers vars; extra slots for 3SAT clause/literal associative strings. */
    pml->silo = init_silo(num_vars + num_clauses + 16);
    pml->flag = 0; /* not solved; do not conflate with assignment truth */
    if (!pml->silo) {
        free(pml->assignment);
        free(pml);
        return NULL;
    }
    return pml;
}

void free_pml(pml_t *pml)
{
    if (!pml) return;
    if (pml->clauses) {
        for (int i = 0; i < pml->num_clauses; i++) {
            free(pml->clauses[i].literals);
        }
        free(pml->clauses);
    }
    free(pml->assignment);
    free_silo(pml->silo);
    free(pml);
}

#ifndef PMLL_NO_MAIN
/* Main with ppm output + semantic peek / SAT bridge smoke demo */
int main(void)
{
    int num_vars = 3;
    int num_clauses = 2;
    const char *val = NULL;
    int idx = -1;
    float sim = 0.0f;
    clause_t *clauses = (clause_t *)malloc((size_t)num_clauses * sizeof(clause_t));
    if (!clauses) {
        fprintf(stderr, "malloc clauses failed\n");
        return 1;
    }

    clauses[0].length = 3;
    clauses[0].literals = (int *)malloc(3 * sizeof(int));
    if (!clauses[0].literals) {
        fprintf(stderr, "malloc literals[0] failed\n");
        free(clauses);
        return 1;
    }
    clauses[0].literals[0] = 1;   /* x1 */
    clauses[0].literals[1] = -2;  /* ~x2 */
    clauses[0].literals[2] = 3;   /* x3 */
    clauses[1].length = 3;
    clauses[1].literals = (int *)malloc(3 * sizeof(int));
    if (!clauses[1].literals) {
        fprintf(stderr, "malloc literals[1] failed\n");
        free(clauses[0].literals);
        free(clauses);
        return 1;
    }
    clauses[1].literals[0] = -1;  /* ~x1 */
    clauses[1].literals[1] = 2;   /* x2 */
    clauses[1].literals[2] = -3;  /* ~x3 */

    pml_t *pml = init_pml(num_vars, num_clauses, clauses);
    if (!pml) {
        fprintf(stderr, "init_pml failed\n");
        free(clauses[0].literals);
        free(clauses[1].literals);
        free(clauses);
        return 1;
    }

    /* Confirm unassigned init (fix for sticky false/flag bug) */
    for (int i = 0; i < num_vars; i++) {
        if (pml->assignment[i] != -1) {
            fprintf(stderr, "init_pml bug: assignment[%d]=%d (want -1)\n",
                    i, pml->assignment[i]);
            free_pml(pml);
            return 1;
        }
    }
    if (pml->flag != 0) {
        fprintf(stderr, "init_pml bug: flag=%d (want 0)\n", pml->flag);
        free_pml(pml);
        return 1;
    }

    /* SAT stack bridge: 3SAT clause tokens → associative memory strings */
    sat_bridge_clause(pml, 0, "first disjunction — contextual meaning in association");
    sat_bridge_clause(pml, 1, "second disjunction — complementary polarity");
    sat_bridge_literal(pml, 1, "positive polarity of x1");
    sat_bridge_literal(pml, -2, "negated x2 in clause 0");

    /* Dual-path peek: key then semantic embedding similarity */
    if (peek(pml->silo, "clause:0", -1, &val, &idx))
        printf("peek(key=clause:0) hit index=%d value=%.60s...\n", idx, val);
    if (peek_semantic(pml->silo, "disjunction complementary polarity", 0.1f,
                      &val, &idx, &sim))
        printf("peek_semantic hit index=%d sim=%.3f value=%.60s...\n", idx, sim, val);

    pml_logic_loop(pml, (int)log2(num_vars > 1 ? num_vars : 2));
    printf("Solution: ");
    for (int i = 0; i < num_vars; i++) {
        if (pml->assignment[i] == 1) printf("x%d=1 ", i + 1);
        else if (pml->assignment[i] == 0) printf("x%d=0 ", i + 1);
        else printf("x%d=? ", i + 1);
    }
    printf("\nflag=%d\n", pml->flag);
    output_to_ppm(pml, "solution.ppm");

    free_pml(pml);
    return 0;
}
#endif /* PMLL_NO_MAIN */
