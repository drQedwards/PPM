/*
 * SAT.c - CDCL SAT solver with PPM visualization helpers.
 *
 * Same algorithm as SAT.py and SAT.pyx: two watched literals, first-UIP
 * clause learning (each learned clause is a resolution consequence of the
 * formula and earlier learned clauses, so it is implied by the formula),
 * activity-based branching, phase saving, restarts whose interval grows by
 * 1.5x, and a model check before SAT is returned. With
 * config.use_clause_learning == false it runs plain DPLL with chronological
 * backtracking. Learned clauses are never deleted and branching is a linear
 * scan. sat_set_proof_output() writes a DRUP proof. SAT is NP-complete; the
 * worst case is exponential. Tests: tests/test_sat_c.py.
 *
 * Build the example program:  cc -O2 -o sat SAT.c -lm
 * Link into another program:  cc -O2 -DSAT_NO_MAIN -c SAT.c
 */
#include "SAT.h"
#include <time.h>
#include <math.h>
#include <ctype.h>
#include <limits.h>

/* ============================================================================
 * Memory Management
 * ============================================================================ */

void* sat_malloc(size_t size) {
    void* ptr = malloc(size);
    if (!ptr && size > 0) {
        fprintf(stderr, "Memory allocation failed\n");
        exit(EXIT_FAILURE);
    }
    return ptr;
}

void* sat_calloc(size_t count, size_t size) {
    void* ptr = calloc(count, size);
    if (!ptr && count > 0 && size > 0) {
        fprintf(stderr, "Memory allocation failed\n");
        exit(EXIT_FAILURE);
    }
    return ptr;
}

void* sat_realloc(void* ptr, size_t new_size) {
    void* new_ptr = realloc(ptr, new_size);
    if (!new_ptr && new_size > 0) {
        fprintf(stderr, "Memory reallocation failed\n");
        exit(EXIT_FAILURE);
    }
    return new_ptr;
}

void sat_free(void* ptr) {
    free(ptr);
}

double get_cpu_time(void) {
    return (double)clock() / CLOCKS_PER_SEC;
}

/* ============================================================================
 * Configuration (max_conflicts == 0 means no limit)
 * ============================================================================ */

SATConfig sat_default_config(void) {
    SATConfig config = {
        .use_vsids = true,
        .use_phase_saving = true,
        .use_clause_learning = true,
        .var_decay = 0.95,
        .clause_decay = 0.999,
        .restart_interval = 100,
        .max_conflicts = 0,
        .enable_visualization = true
    };
    return config;
}

SATConfig sat_minisat_config(void) {
    SATConfig config = {
        .use_vsids = true,
        .use_phase_saving = true,
        .use_clause_learning = true,
        .var_decay = 0.95,
        .clause_decay = 0.999,
        .restart_interval = 100,
        .max_conflicts = 100000,
        .enable_visualization = false
    };
    return config;
}

/* Named for compatibility. Same algorithm as the others (no LBD, no clause
 * deletion), with faster variable decay and shorter initial restarts. */
SATConfig sat_glucose_config(void) {
    SATConfig config = sat_minisat_config();
    config.var_decay = 0.8;
    config.restart_interval = 50;
    return config;
}

/* ============================================================================
 * CNF Management
 * ============================================================================ */

CNF* cnf_create(size_t num_vars) {
    CNF* cnf = (CNF*)sat_calloc(1, sizeof(CNF));
    cnf->num_vars = num_vars;
    cnf->clause_capacity = 100;
    cnf->clauses = (Clause*)sat_malloc(cnf->clause_capacity * sizeof(Clause));
    cnf->var_states = (VarState*)sat_calloc(num_vars + 1, sizeof(VarState));
    for (size_t i = 0; i <= num_vars; i++) {
        cnf->var_states[i].activity = 0.0;
        cnf->var_states[i].decision_level = -1;
        cnf->var_states[i].antecedent = -1;
        cnf->var_states[i].phase_saving = false;
    }
    return cnf;
}

void cnf_destroy(CNF* cnf) {
    if (!cnf) return;
    for (size_t i = 0; i < cnf->num_clauses; i++) {
        sat_free(cnf->clauses[i].literals);
    }
    sat_free(cnf->clauses);
    sat_free(cnf->var_states);
    sat_free(cnf);
}

static bool literal_in_range(const CNF* cnf, int lit) {
    return lit != 0 && lit != INT_MIN && (size_t)abs(lit) <= cnf->num_vars;
}

/* Append a clause; size 0 adds the empty clause. Literals must be in range. */
static SATResult cnf_push_clause(CNF* cnf, const int* literals, size_t size, bool learned) {
    for (size_t i = 0; i < size; i++) {
        if (!literal_in_range(cnf, literals[i])) {
            return SAT_ERROR_INVALID_INPUT;
        }
    }
    if (cnf->num_clauses >= cnf->clause_capacity) {
        cnf->clause_capacity = cnf->clause_capacity ? cnf->clause_capacity * 2 : 16;
        cnf->clauses = (Clause*)sat_realloc(cnf->clauses, cnf->clause_capacity * sizeof(Clause));
    }
    Clause* clause = &cnf->clauses[cnf->num_clauses];
    clause->size = size;
    clause->capacity = size;
    clause->literals = size ? (Literal*)sat_malloc(size * sizeof(Literal)) : NULL;
    clause->learned = learned;
    clause->activity = 0.0;
    for (size_t i = 0; i < size; i++) {
        clause->literals[i].var = literals[i];
        clause->literals[i].value = false;
        int var = abs(literals[i]);
        if (literals[i] > 0) {
            cnf->var_states[var].activity += 0.01; /* initial activity, as before */
        }
    }
    cnf->num_clauses++;
    return SAT_SUCCESS;
}

/* Rejects size 0 (as before) and out-of-range literals. */
SATResult cnf_add_clause(CNF* cnf, int* literals, size_t size) {
    if (!cnf || !literals || size == 0) {
        return SAT_ERROR_INVALID_INPUT;
    }
    return cnf_push_clause(cnf, literals, size, false);
}

/* Copies clause; a clause with size 0 is the empty clause (formula is UNSAT). */
SATResult cnf_add_clause_array(CNF* cnf, Clause* clause) {
    if (!cnf || !clause || (clause->size > 0 && !clause->literals)) {
        return SAT_ERROR_INVALID_INPUT;
    }
    int* lits = (int*)sat_malloc((clause->size ? clause->size : 1) * sizeof(int));
    for (size_t i = 0; i < clause->size; i++) {
        lits[i] = clause->literals[i].var;
    }
    SATResult r = cnf_push_clause(cnf, lits, clause->size, clause->learned);
    sat_free(lits);
    return r;
}

CNF* cnf_copy(const CNF* original) {
    if (!original) return NULL;
    CNF* cnf = cnf_create(original->num_vars);
    for (size_t i = 0; i < original->num_clauses; i++) {
        cnf_add_clause_array(cnf, &original->clauses[i]);
    }
    for (size_t v = 0; v <= original->num_vars; v++) {
        cnf->var_states[v] = original->var_states[v];
    }
    return cnf;
}

/* Remove duplicate literals and drop tautological clauses, in place. */
SATResult cnf_simplify(CNF* cnf) {
    if (!cnf) return SAT_ERROR_INVALID_INPUT;
    size_t out = 0;
    for (size_t i = 0; i < cnf->num_clauses; i++) {
        Clause* c = &cnf->clauses[i];
        size_t k = 0;
        bool tautology = false;
        for (size_t j = 0; j < c->size && !tautology; j++) {
            int lit = c->literals[j].var;
            bool dup = false;
            for (size_t t = 0; t < k; t++) {
                if (c->literals[t].var == lit) dup = true;
                if (c->literals[t].var == -lit) tautology = true;
            }
            if (!dup && !tautology) c->literals[k++] = c->literals[j];
        }
        if (tautology) {
            sat_free(c->literals);
            continue;
        }
        c->size = k;
        cnf->clauses[out++] = *c;
    }
    cnf->num_clauses = out;
    return SAT_SUCCESS;
}

/* ============================================================================
 * Watch List (standalone helpers; the solver uses its own arrays in SATInternal)
 * ============================================================================ */

/* Each array has num_vars + 2 slots; the last one holds a sentinel so that
 * watch_list_destroy can find the end and free every node. */
static WatchNode watch_end_sentinel;

WatchList* watch_list_create(size_t num_vars) {
    WatchList* watches = (WatchList*)sat_calloc(1, sizeof(WatchList));
    watches->pos_watches = (WatchNode**)sat_calloc(num_vars + 2, sizeof(WatchNode*));
    watches->neg_watches = (WatchNode**)sat_calloc(num_vars + 2, sizeof(WatchNode*));
    watches->pos_watches[num_vars + 1] = &watch_end_sentinel;
    watches->neg_watches[num_vars + 1] = &watch_end_sentinel;
    return watches;
}

static void free_watch_array(WatchNode** heads) {
    if (!heads) return;
    for (size_t v = 0; heads[v] != &watch_end_sentinel; v++) {
        WatchNode* node = heads[v];
        while (node) {
            WatchNode* next = node->next;
            sat_free(node);
            node = next;
        }
    }
    sat_free(heads);
}

void watch_list_destroy(WatchList* watches) {
    if (!watches) return;
    free_watch_array(watches->pos_watches);
    free_watch_array(watches->neg_watches);
    sat_free(watches);
}

static WatchNode** watch_head(WatchList* watches, int lit) {
    return lit > 0 ? &watches->pos_watches[lit] : &watches->neg_watches[-lit];
}

void watch_clause(WatchList* watches, size_t clause_idx, int lit1, int lit2) {
    if (!watches) return;
    int lits[2] = {lit1, lit2};
    for (int i = 0; i < 2; i++) {
        if (lits[i] == 0 || (i == 1 && lit2 == lit1)) continue;
        WatchNode* node = (WatchNode*)sat_malloc(sizeof(WatchNode));
        node->clause_idx = clause_idx;
        WatchNode** head = watch_head(watches, lits[i]);
        node->next = *head;
        *head = node;
    }
}

void unwatch_clause(WatchList* watches, size_t clause_idx, int lit) {
    if (!watches || lit == 0) return;
    WatchNode** link = watch_head(watches, lit);
    while (*link) {
        if ((*link)->clause_idx == clause_idx) {
            WatchNode* dead = *link;
            *link = dead->next;
            sat_free(dead);
            return;
        }
        link = &(*link)->next;
    }
}

/* ============================================================================
 * Solver state
 * ============================================================================ */

typedef struct {
    int* data;
    size_t size;
    size_t cap;
} IVec;

static void ivec_push(IVec* v, int x) {
    if (v->size == v->cap) {
        v->cap = v->cap ? v->cap * 2 : 4;
        v->data = (int*)sat_realloc(v->data, v->cap * sizeof(int));
    }
    v->data[v->size++] = x;
}

struct SATInternal {
    size_t n;
    IVec* clauses;        /* literal codes; positions 0 and 1 are the watches */
    size_t nclauses;
    size_t ccap;
    size_t num_original;  /* clauses [0, num_original) come from the CNF */
    IVec* watches;        /* per literal code: indices of clauses watching it */
    int* reason;          /* per variable: clause index, -1 for decisions / none */
    int* trail_lim;       /* trail_lim[i]: trail size when level i+1 began */
    char* flipped;        /* DPLL mode: decision at level i already flipped */
    char* seen;
    IVec tmp;
    size_t qhead;
    double var_inc;
    int conflict;         /* last conflict clause index, -1 if none */
    bool has_empty;
    FILE* proof;
};

/* Literal x -> 2x, -x -> 2x + 1. */
static inline int lit_code(int lit) { return lit > 0 ? 2 * lit : -2 * lit + 1; }
static inline int code_lit(int code) { return (code & 1) ? -(code >> 1) : (code >> 1); }

static inline int code_value(const SATSolver* s, int code) {
    int a = s->assignment[code >> 1];
    return a < 0 ? -1 : (a ^ (code & 1));   /* 1 true, 0 false, -1 unassigned */
}

static void internal_free_clauses(SATInternal* in) {
    for (size_t i = 0; i < in->nclauses; i++) sat_free(in->clauses[i].data);
    sat_free(in->clauses);
    in->clauses = NULL;
    in->nclauses = in->ccap = in->num_original = 0;
    if (in->watches) {
        for (size_t c = 0; c < 2 * (in->n + 1); c++) {
            sat_free(in->watches[c].data);
            in->watches[c].data = NULL;
            in->watches[c].size = in->watches[c].cap = 0;
        }
    }
}

static size_t internal_store_tmp(SATInternal* in) {
    if (in->nclauses == in->ccap) {
        size_t ncap = in->ccap ? in->ccap * 2 : 16;
        in->clauses = (IVec*)sat_realloc(in->clauses, ncap * sizeof(IVec));
        memset(in->clauses + in->ccap, 0, (ncap - in->ccap) * sizeof(IVec));
        in->ccap = ncap;
    }
    size_t idx = in->nclauses++;
    for (size_t i = 0; i < in->tmp.size; i++) ivec_push(&in->clauses[idx], in->tmp.data[i]);
    if (in->tmp.size >= 2) {
        ivec_push(&in->watches[in->tmp.data[0]], (int)idx);
        ivec_push(&in->watches[in->tmp.data[1]], (int)idx);
    }
    return idx;
}

/* Rebuild the clause store from the CNF: merge duplicate literals, drop tautologies. */
static void internal_load(SATSolver* s) {
    SATInternal* in = s->internal;
    internal_free_clauses(in);
    in->has_empty = false;
    for (size_t i = 0; i < s->cnf->num_clauses; i++) {
        const Clause* c = &s->cnf->clauses[i];
        bool tautology = false;
        in->tmp.size = 0;
        for (size_t j = 0; j < c->size && !tautology; j++) {
            int code = lit_code(c->literals[j].var);
            bool dup = false;
            for (size_t t = 0; t < in->tmp.size; t++) {
                if (in->tmp.data[t] == code) dup = true;
                if (in->tmp.data[t] == (code ^ 1)) tautology = true;
            }
            if (!dup && !tautology) ivec_push(&in->tmp, code);
        }
        if (tautology) continue;
        if (in->tmp.size == 0) in->has_empty = true;
        internal_store_tmp(in);
    }
    in->num_original = in->nclauses;
}

static void proof_clause(SATInternal* in, const int* codes, size_t size) {
    if (!in->proof) return;
    for (size_t i = 0; i < size; i++) fprintf(in->proof, "%d ", code_lit(codes[i]));
    fprintf(in->proof, "0\n");
}

void sat_set_proof_output(SATSolver* solver, FILE* proof) {
    if (solver && solver->internal) solver->internal->proof = proof;
}

SATSolver* sat_solver_create(CNF* cnf) {
    return sat_solver_create_with_config(cnf, sat_default_config());
}

SATSolver* sat_solver_create_with_config(CNF* cnf, SATConfig config) {
    SATSolver* solver = (SATSolver*)sat_calloc(1, sizeof(SATSolver));
    size_t n = cnf->num_vars;
    solver->cnf = cnf;
    solver->config = config;
    solver->assignment = (int*)sat_malloc((n + 1) * sizeof(int));
    solver->trail = (int*)sat_malloc((n + 1) * sizeof(int));
    solver->decision_level = (int*)sat_calloc(n + 1, sizeof(int));
    solver->watches = watch_list_create(n);
    SATInternal* in = (SATInternal*)sat_calloc(1, sizeof(SATInternal));
    in->n = n;
    in->watches = (IVec*)sat_calloc(2 * (n + 1), sizeof(IVec));
    in->reason = (int*)sat_malloc((n + 1) * sizeof(int));
    in->trail_lim = (int*)sat_calloc(n + 1, sizeof(int));
    in->flipped = (char*)sat_calloc(n + 2, sizeof(char));
    in->seen = (char*)sat_calloc(n + 1, sizeof(char));
    in->var_inc = 1.0;
    in->conflict = -1;
    solver->internal = in;
    for (size_t i = 0; i <= n; i++) {
        solver->assignment[i] = -1;
        solver->decision_level[i] = -1;
        in->reason[i] = -1;
    }
    return solver;
}

void sat_solver_destroy(SATSolver* solver) {
    if (!solver) return;
    watch_list_destroy(solver->watches);
    SATInternal* in = solver->internal;
    if (in) {
        internal_free_clauses(in);
        sat_free(in->watches);
        sat_free(in->reason);
        sat_free(in->trail_lim);
        sat_free(in->flipped);
        sat_free(in->seen);
        sat_free(in->tmp.data);
        sat_free(in);
    }
    sat_free(solver->assignment);
    sat_free(solver->trail);
    sat_free(solver->decision_level);
    sat_free(solver);
}

/* ============================================================================
 * Assignment, propagation, analysis
 * ============================================================================ */

bool is_clause_satisfied(const Clause* clause, const int* assignment) {
    for (size_t i = 0; i < clause->size; i++) {
        int var = abs(clause->literals[i].var);
        bool sign = clause->literals[i].var > 0;
        if (assignment[var] != -1 && ((assignment[var] == 1) == sign)) {
            return true;
        }
    }
    return false;
}

bool is_clause_unit(const Clause* clause, const int* assignment, int* unit_lit) {
    int unassigned_count = 0;
    int unassigned_lit = 0;
    for (size_t i = 0; i < clause->size; i++) {
        int var = abs(clause->literals[i].var);
        if (assignment[var] == -1) {
            unassigned_count++;
            unassigned_lit = clause->literals[i].var;
        } else {
            bool sign = clause->literals[i].var > 0;
            if ((assignment[var] == 1) == sign) {
                return false;
            }
        }
    }
    if (unassigned_count == 1 && unit_lit) {
        *unit_lit = unassigned_lit;
        return true;
    }
    return false;
}

/* Assign var at the current decision level; antecedent is a clause index or -1. */
void assign_variable(SATSolver* solver, int var, bool value, int antecedent) {
    solver->assignment[var] = value ? 1 : 0;
    solver->decision_level[var] = solver->current_level;
    solver->cnf->var_states[var].decision_level = solver->current_level;
    solver->cnf->var_states[var].antecedent = antecedent;
    solver->internal->reason[var] = antecedent;
    solver->trail[solver->trail_size++] = value ? var : -var;
    if (solver->config.use_phase_saving) {
        solver->cnf->var_states[var].phase_saving = value;
    }
    solver->cnf->stats.propagations++;
}

void unassign_variable(SATSolver* solver, int var) {
    solver->assignment[var] = -1;
    solver->decision_level[var] = -1;
    solver->cnf->var_states[var].decision_level = -1;
    solver->cnf->var_states[var].antecedent = -1;
    solver->internal->reason[var] = -1;
}

static inline void assign_code(SATSolver* s, int code, int why) {
    assign_variable(s, code >> 1, (code & 1) == 0, why);
}

void backtrack(SATSolver* solver, int level) {
    SATInternal* in = solver->internal;
    if (level < 0) level = 0;
    if (solver->current_level > level) {
        size_t lim = (size_t)in->trail_lim[level];
        while (solver->trail_size > lim) {
            unassign_variable(solver, abs(solver->trail[--solver->trail_size]));
        }
        solver->current_level = level;
    }
    if (in->qhead > solver->trail_size) in->qhead = solver->trail_size;
}

/* Two-watched-literal propagation. Returns a falsified clause index or -1. */
static int propagate(SATSolver* s) {
    SATInternal* in = s->internal;
    while (in->qhead < s->trail_size) {
        int false_code = lit_code(s->trail[in->qhead++]) ^ 1;
        IVec* ws = &in->watches[false_code];
        size_t i = 0, j = 0;
        while (i < ws->size) {
            int ci = ws->data[i++];
            IVec* c = &in->clauses[ci];
            if (c->data[0] == false_code) {
                c->data[0] = c->data[1];
                c->data[1] = false_code;
            }
            if (code_value(s, c->data[0]) == 1) {
                ws->data[j++] = ci;
                continue;
            }
            bool found = false;
            for (size_t k = 2; k < c->size; k++) {
                if (code_value(s, c->data[k]) != 0) {
                    int t = c->data[1];
                    c->data[1] = c->data[k];
                    c->data[k] = t;
                    ivec_push(&in->watches[c->data[1]], ci);
                    found = true;
                    break;
                }
            }
            if (found) continue;
            ws->data[j++] = ci;
            if (code_value(s, c->data[0]) == 0) {
                while (i < ws->size) ws->data[j++] = ws->data[i++];
                ws->size = j;
                in->qhead = s->trail_size;
                return ci;
            }
            assign_code(s, c->data[0], ci);
        }
        ws->size = j;
    }
    return -1;
}

/* Watched-literal unit propagation; false on conflict (the conflict clause is
 * remembered for analyze_conflict). */
bool unit_propagate(SATSolver* solver) {
    solver->internal->conflict = propagate(solver);
    return solver->internal->conflict < 0;
}

void update_vsids(SATSolver* solver, int var) {
    VarState* vs = solver->cnf->var_states;
    vs[var].activity += solver->internal->var_inc;
    if (vs[var].activity > 1e100) {
        for (size_t v = 1; v <= solver->cnf->num_vars; v++) vs[v].activity *= 1e-100;
        solver->internal->var_inc *= 1e-100;
    }
}

/* MiniSat-style decay: later bumps weigh more, which decays older activity. */
void decay_activities(SATSolver* solver) {
    if (solver->config.var_decay > 0.0) solver->internal->var_inc /= solver->config.var_decay;
}

/* First-UIP analysis of conflict clause confl into in->tmp (asserting literal
 * first, highest-level literal second). Returns the backtrack level. */
static int analyze(SATSolver* s, int confl) {
    SATInternal* in = s->internal;
    int counter = 0;
    size_t index = s->trail_size;
    int pvar = 0, p = 0, ci = confl;
    in->tmp.size = 0;
    ivec_push(&in->tmp, 0);
    for (;;) {
        IVec* c = &in->clauses[ci];
        for (size_t k = 0; k < c->size; k++) {
            int q = c->data[k], v = q >> 1;
            if (v == pvar || in->seen[v] || s->decision_level[v] == 0) continue;
            in->seen[v] = 1;
            if (s->config.use_vsids) update_vsids(s, v);
            if (s->decision_level[v] >= s->current_level) counter++;
            else ivec_push(&in->tmp, q);
        }
        do {
            index--;
        } while (!in->seen[abs(s->trail[index])]);
        p = lit_code(s->trail[index]);
        pvar = p >> 1;
        in->seen[pvar] = 0;
        if (--counter == 0) break;
        ci = in->reason[pvar];
    }
    in->tmp.data[0] = p ^ 1;
    for (size_t k = 1; k < in->tmp.size; k++) in->seen[in->tmp.data[k] >> 1] = 0;
    int bt = 0;
    if (in->tmp.size > 1) {
        size_t best = 1;
        for (size_t k = 2; k < in->tmp.size; k++) {
            if (s->decision_level[in->tmp.data[k] >> 1] > s->decision_level[in->tmp.data[best] >> 1]) best = k;
        }
        int t = in->tmp.data[1];
        in->tmp.data[1] = in->tmp.data[best];
        in->tmp.data[best] = t;
        bt = s->decision_level[in->tmp.data[1] >> 1];
    }
    return bt;
}

/* Public wrapper: analyzes the last conflict found by unit_propagate. Fills
 * learned_clause (literals allocated with sat_malloc; caller frees them) and
 * the backtrack level. Size 0 and level -1 when there is nothing to analyze. */
void analyze_conflict(SATSolver* solver, Clause* learned_clause, int* backtrack_level) {
    SATInternal* in = solver->internal;
    learned_clause->size = 0;
    learned_clause->capacity = 0;
    learned_clause->literals = NULL;
    learned_clause->learned = true;
    learned_clause->activity = 0.0;
    if (in->conflict < 0 || solver->current_level == 0) {
        *backtrack_level = -1;
        return;
    }
    *backtrack_level = analyze(solver, in->conflict);
    learned_clause->literals = (Literal*)sat_malloc(in->tmp.size * sizeof(Literal));
    for (size_t k = 0; k < in->tmp.size; k++) {
        learned_clause->literals[k].var = code_lit(in->tmp.data[k]);
        learned_clause->literals[k].value = false;
    }
    learned_clause->size = learned_clause->capacity = in->tmp.size;
}

void restart(SATSolver* solver) {
    backtrack(solver, 0);
}

/* Unassigned variable with the highest activity (ties: lowest index), or the
 * lowest unassigned index when use_vsids is off. 0 when all are assigned. */
int choose_branching_variable(SATSolver* solver) {
    int best = 0;
    double best_act = -1.0;
    for (size_t v = 1; v <= solver->cnf->num_vars; v++) {
        if (solver->assignment[v] != -1) continue;
        if (!solver->config.use_vsids) return (int)v;
        if (solver->cnf->var_states[v].activity > best_act) {
            best_act = solver->cnf->var_states[v].activity;
            best = (int)v;
        }
    }
    return best;
}

static void new_level(SATSolver* s, int code, char was_flipped) {
    SATInternal* in = s->internal;
    in->trail_lim[s->current_level] = (int)s->trail_size;
    s->current_level++;
    in->flipped[s->current_level] = was_flipped;
    assign_code(s, code, -1);
}

/* DPLL mode: emit the clause negating the unflipped decisions (RUP), then flip
 * the deepest unflipped decision. False when none is left (UNSAT). */
static bool flip_last_decision(SATSolver* s) {
    SATInternal* in = s->internal;
    in->tmp.size = 0;
    for (int l = 1; l <= s->current_level; l++) {
        if (!in->flipped[l]) ivec_push(&in->tmp, lit_code(s->trail[in->trail_lim[l - 1]]) ^ 1);
    }
    proof_clause(in, in->tmp.data, in->tmp.size);
    int lvl = s->current_level;
    while (lvl > 0 && in->flipped[lvl]) lvl--;
    if (lvl == 0) return false;
    int dec = lit_code(s->trail[in->trail_lim[lvl - 1]]);
    backtrack(s, lvl - 1);
    new_level(s, dec ^ 1, 1);
    return true;
}

static bool model_satisfies_original(const SATSolver* s) {
    const SATInternal* in = s->internal;
    for (size_t ci = 0; ci < in->num_original; ci++) {
        const IVec* c = &in->clauses[ci];
        bool ok = false;
        for (size_t k = 0; k < c->size && !ok; k++) ok = code_value(s, c->data[k]) == 1;
        if (!ok) return false;
    }
    return true;
}

static SATResult unsat(SATSolver* s) {
    if (s->internal->proof) fprintf(s->internal->proof, "0\n");
    return SAT_UNSATISFIABLE;
}

/* The search: CDCL when learning is true, plain DPLL otherwise. */
static SATResult search(SATSolver* s, bool learning) {
    SATInternal* in = s->internal;
    size_t n = s->cnf->num_vars;
    for (size_t v = 0; v <= n; v++) unassign_variable(s, (int)v);
    s->trail_size = 0;
    s->current_level = 0;
    in->qhead = 0;
    in->conflict = -1;
    internal_load(s);
    if (in->has_empty) return unsat(s);
    for (size_t ci = 0; ci < in->nclauses; ci++) {
        if (in->clauses[ci].size != 1) continue;
        int code = in->clauses[ci].data[0];
        int val = code_value(s, code);
        if (val == 0) return unsat(s);
        if (val < 0) assign_code(s, code, (int)ci);
    }
    size_t conflicts = 0, since_restart = 0;
    size_t restart_limit = s->config.restart_interval ? s->config.restart_interval : 1;
    for (;;) {
        int confl = propagate(s);
        in->conflict = confl;
        if (confl >= 0) {
            conflicts++;
            since_restart++;
            s->cnf->stats.conflicts++;
            if (s->current_level == 0) return unsat(s);
            if (s->config.max_conflicts && conflicts >= s->config.max_conflicts) {
                backtrack(s, 0);
                return SAT_ERROR_TIMEOUT;
            }
            if (learning) {
                int bt = analyze(s, confl);
                backtrack(s, bt);
                size_t idx = internal_store_tmp(in);
                proof_clause(in, in->tmp.data, in->tmp.size);
                assign_code(s, in->tmp.data[0], (int)idx);
                s->cnf->stats.learned_clauses++;
                if (s->config.use_vsids) decay_activities(s);
            } else if (!flip_last_decision(s)) {
                return SAT_UNSATISFIABLE;  /* empty clause already written */
            }
            continue;
        }
        if (learning && since_restart >= restart_limit) {
            restart(s);
            since_restart = 0;
            if (restart_limit < ((size_t)1 << 40)) restart_limit = restart_limit * 3 / 2 + 1;
            continue;
        }
        int v = choose_branching_variable(s);
        if (v == 0) {
            if (!model_satisfies_original(s)) {
                fprintf(stderr, "SAT.c internal error: model does not satisfy the formula\n");
                abort();
            }
            return SAT_SUCCESS;
        }
        s->cnf->stats.decisions++;
        bool phase = s->config.use_phase_saving && s->cnf->var_states[v].phase_saving;
        new_level(s, phase ? 2 * v : 2 * v + 1, 0);
    }
}

/* Kept for API compatibility: var_idx is ignored. Plain DPLL; true when SAT. */
bool dpll(SATSolver* solver, size_t var_idx) {
    (void)var_idx;
    return search(solver, false) == SAT_SUCCESS;
}

/* CDCL with first-UIP learning; true when SAT. */
bool dpll_with_learning(SATSolver* solver) {
    return search(solver, true) == SAT_SUCCESS;
}

/* Assign pure literals (all occurrences in not-yet-satisfied clauses have one
 * sign) at decision level 0. Satisfiability-preserving, but pure literals are
 * not implied by the formula, so sat_solve does not use this; it is a helper.
 * Returns true if anything was assigned. */
bool pure_literal_elimination(SATSolver* solver) {
    if (solver->current_level != 0) return false;
    size_t n = solver->cnf->num_vars;
    char* sign = (char*)sat_calloc(n + 1, 1);  /* bit 1: positive seen, bit 2: negative */
    for (size_t i = 0; i < solver->cnf->num_clauses; i++) {
        const Clause* c = &solver->cnf->clauses[i];
        if (is_clause_satisfied(c, solver->assignment)) continue;
        for (size_t j = 0; j < c->size; j++) {
            int lit = c->literals[j].var;
            if (solver->assignment[abs(lit)] == -1) sign[abs(lit)] |= lit > 0 ? 1 : 2;
        }
    }
    bool any = false;
    for (size_t v = 1; v <= n; v++) {
        if (sign[v] == 1 || sign[v] == 2) {
            assign_variable(solver, (int)v, sign[v] == 1, -1);
            any = true;
        }
    }
    sat_free(sign);
    return any;
}

/* ============================================================================
 * Main Solving Interface
 * ============================================================================ */

SATResult sat_solve(SATSolver* solver) {
    if (!solver || !solver->cnf) return SAT_ERROR_INVALID_INPUT;
    clock_t start = clock();
    SATResult r = search(solver, solver->config.use_clause_learning);
    solver->cnf->stats.cpu_time = ((double)(clock() - start)) / CLOCKS_PER_SEC;
    return r;
}

/* Solve under assumptions (literals that must hold) by solving a copy with the
 * assumptions added as unit clauses. On SAT the model is copied to solver->assignment. */
SATResult sat_solve_with_assumptions(SATSolver* solver, int* assumptions, size_t num_assumptions) {
    if (!solver || (num_assumptions && !assumptions)) return SAT_ERROR_INVALID_INPUT;
    CNF* copy = cnf_copy(solver->cnf);
    for (size_t i = 0; i < num_assumptions; i++) {
        if (cnf_add_clause(copy, &assumptions[i], 1) != SAT_SUCCESS) {
            cnf_destroy(copy);
            return SAT_ERROR_INVALID_INPUT;
        }
    }
    SATSolver* inner = sat_solver_create_with_config(copy, solver->config);
    SATResult r = sat_solve(inner);
    if (r == SAT_SUCCESS) {
        memcpy(solver->assignment, inner->assignment, (copy->num_vars + 1) * sizeof(int));
    }
    solver->cnf->stats.decisions += copy->stats.decisions;
    solver->cnf->stats.propagations += copy->stats.propagations;
    solver->cnf->stats.conflicts += copy->stats.conflicts;
    solver->cnf->stats.learned_clauses += copy->stats.learned_clauses;
    sat_solver_destroy(inner);
    cnf_destroy(copy);
    return r;
}

/* Decides the formula with no conflict limit. assignment needs num_vars + 1 ints. */
bool sat_is_satisfiable(CNF* cnf, int* assignment) {
    SATConfig config = sat_default_config();
    config.max_conflicts = 0;
    SATSolver* solver = sat_solver_create_with_config(cnf, config);
    SATResult result = sat_solve(solver);
    if (result == SAT_SUCCESS && assignment) {
        for (size_t i = 0; i <= cnf->num_vars; i++) {
            assignment[i] = solver->assignment[i];
        }
    }
    sat_solver_destroy(solver);
    return result == SAT_SUCCESS;
}

/* SAT_SUCCESS when every clause has a true literal under assignment. */
SATResult validate_solution(const CNF* cnf, const int* assignment) {
    if (!cnf || !assignment) return SAT_ERROR_INVALID_INPUT;
    for (size_t i = 0; i < cnf->num_clauses; i++) {
        if (!is_clause_satisfied(&cnf->clauses[i], assignment)) return SAT_UNSATISFIABLE;
    }
    return SAT_SUCCESS;
}

/* Graphviz DOT of the current implication graph: an edge u -> v when u's
 * literal appears in the reason clause of v. */
SATResult generate_implication_graph(const SATSolver* solver, const char* filename) {
    if (!solver || !filename) return SAT_ERROR_INVALID_INPUT;
    FILE* fp = fopen(filename, "w");
    if (!fp) return SAT_ERROR_MEMORY;
    const SATInternal* in = solver->internal;
    fprintf(fp, "digraph implications {\n");
    for (size_t t = 0; t < solver->trail_size; t++) {
        int lit = solver->trail[t];
        int v = abs(lit);
        fprintf(fp, "  x%d [label=\"%sx%d@%d\"];\n", v, lit < 0 ? "-" : "", v, solver->decision_level[v]);
        int r = in->reason[v];
        if (r < 0 || (size_t)r >= in->nclauses) continue;
        const IVec* c = &in->clauses[r];
        for (size_t k = 0; k < c->size; k++) {
            int u = c->data[k] >> 1;
            if (u != v) fprintf(fp, "  x%d -> x%d;\n", u, v);
        }
    }
    fprintf(fp, "}\n");
    fclose(fp);
    return SAT_SUCCESS;
}

/* ============================================================================
 * PPM Visualization
 * ============================================================================ */

typedef struct {
    uint8_t r, g, b;
} Pixel;

SATResult generate_ppm_visualization(const SATSolver* solver, const char* filename) {
    if (!solver || !filename) {
        return SAT_ERROR_INVALID_INPUT;
    }
    
    FILE* fp = fopen(filename, "wb");
    if (!fp) {
        return SAT_ERROR_MEMORY;
    }
    
    size_t height = solver->cnf->num_clauses;
    size_t width = solver->cnf->num_vars;
    
    // Scale for visibility (minimum 100x100 pixels)
    int scale = 1;
    if (height < 100 || width < 100) {
        scale = fmax(100.0 / height, 100.0 / width);
        scale = fmin(scale, 10); // Max scale factor
    }
    
    size_t img_height = height * scale;
    size_t img_width = width * scale;
    
    // PPM header
    fprintf(fp, "P6\n%zu %zu\n255\n", img_width, img_height);
    
    // Generate image
    for (size_t y = 0; y < img_height; y++) {
        for (size_t x = 0; x < img_width; x++) {
            size_t clause_idx = y / scale;
            size_t var_idx = x / scale + 1;
            
            Pixel pixel = {0, 0, 0}; // Black background
            
            if (clause_idx < height && var_idx <= width) {
                Clause* clause = &solver->cnf->clauses[clause_idx];
                
                // Check if variable appears in clause
                bool found = false;
                bool positive = false;
                
                for (size_t i = 0; i < clause->size; i++) {
                    int lit_var = abs(clause->literals[i].var);
                    if (lit_var == (int)var_idx) {
                        found = true;
                        positive = clause->literals[i].var > 0;
                        break;
                    }
                }
                
                if (found) {
                    int assignment_val = solver->assignment[var_idx];
                    
                    if (assignment_val == -1) {
                        // Unassigned - Blue shades
                        pixel.b = positive ? 255 : 128;
                    } else if ((assignment_val == 1 && positive) || 
                              (assignment_val == 0 && !positive)) {
                        // Satisfied literal - Green
                        pixel.g = 255;
                        
                        // Add brightness based on activity
                        double activity = solver->cnf->var_states[var_idx].activity;
                        int brightness = (int)(activity * 50);
                        pixel.r = fmin(brightness, 255);
                    } else {
                        // Unsatisfied literal - Red
                        pixel.r = 255;
                    }
                    
                    // Mark learned clauses differently
                    if (clause->learned) {
                        pixel.r = pixel.r / 2 + 128;
                        pixel.g = pixel.g / 2 + 128;
                        pixel.b = pixel.b / 2 + 128;
                    }
                }
            }
            
            fwrite(&pixel, sizeof(Pixel), 1, fp);
        }
    }
    
    fclose(fp);
    return SAT_SUCCESS;
}

SATResult generate_clause_heatmap(const CNF* cnf, const int* assignment, const char* filename) {
    if (!cnf || !filename) {
        return SAT_ERROR_INVALID_INPUT;
    }
    
    FILE* fp = fopen(filename, "wb");
    if (!fp) {
        return SAT_ERROR_MEMORY;
    }
    
    // Create a grid showing clause satisfaction levels
    size_t size = (size_t)sqrt(cnf->num_clauses) + 1;
    int scale = fmax(1, 500 / size);
    size_t img_size = size * scale;
    
    fprintf(fp, "P6\n%zu %zu\n255\n", img_size, img_size);
    
    for (size_t y = 0; y < img_size; y++) {
        for (size_t x = 0; x < img_size; x++) {
            size_t clause_idx = (y / scale) * size + (x / scale);
            
            Pixel pixel = {32, 32, 32}; // Dark gray background
            
            if (clause_idx < cnf->num_clauses) {
                Clause* clause = &cnf->clauses[clause_idx];
                
                if (assignment) {
                    if (is_clause_satisfied(clause, assignment)) {
                        // Green gradient based on how many literals are satisfied
                        int sat_count = 0;
                        for (size_t i = 0; i < clause->size; i++) {
                            int var = abs(clause->literals[i].var);
                            bool sign = clause->literals[i].var > 0;
                            if (assignment[var] != -1 && ((assignment[var] == 1) == sign)) {
                                sat_count++;
                            }
                        }
                        int intensity = 128 + (127 * sat_count) / clause->size;
                        pixel.g = intensity;
                    } else {
                        // Red gradient based on how many literals are unsatisfied
                        int unsat_count = 0;
                        for (size_t i = 0; i < clause->size; i++) {
                            int var = abs(clause->literals[i].var);
                            bool sign = clause->literals[i].var > 0;
                            if (assignment[var] != -1 && ((assignment[var] == 1) != sign)) {
                                unsat_count++;
                            }
                        }
                        int intensity = 128 + (127 * unsat_count) / clause->size;
                        pixel.r = intensity;
                    }
                } else {
                    // No assignment - show clause size with blue
                    int intensity = fmin(255, 50 + clause->size * 30);
                    pixel.b = intensity;
                }
            }
            
            fwrite(&pixel, sizeof(Pixel), 1, fp);
        }
    }
    
    fclose(fp);
    return SAT_SUCCESS;
}

SATResult generate_variable_activity_map(const SATSolver* solver, const char* filename) {
    if (!solver || !filename) {
        return SAT_ERROR_INVALID_INPUT;
    }
    
    FILE* fp = fopen(filename, "wb");
    if (!fp) {
        return SAT_ERROR_MEMORY;
    }
    
    // Create a grid of variables showing their activity levels
    size_t size = (size_t)sqrt(solver->cnf->num_vars) + 1;
    int scale = fmax(1, 500 / size);
    size_t img_size = size * scale;
    
    // Find max activity for normalization
    double max_activity = 0.0;
    for (size_t i = 1; i <= solver->cnf->num_vars; i++) {
        if (solver->cnf->var_states[i].activity > max_activity) {
            max_activity = solver->cnf->var_states[i].activity;
        }
    }
    if (max_activity == 0.0) max_activity = 1.0;
    
    fprintf(fp, "P6\n%zu %zu\n255\n", img_size, img_size);
    
    for (size_t y = 0; y < img_size; y++) {
        for (size_t x = 0; x < img_size; x++) {
            size_t var_idx = (y / scale) * size + (x / scale) + 1;
            
            Pixel pixel = {0, 0, 0}; // Black background
            
            if (var_idx <= solver->cnf->num_vars) {
                double activity = solver->cnf->var_states[var_idx].activity;
                int intensity = (int)(255 * (activity / max_activity));
                
                int assignment_val = solver->assignment[var_idx];
                if (assignment_val == 1) {
                    // True - Green channel
                    pixel.g = intensity;
                    pixel.r = intensity / 4;
                } else if (assignment_val == 0) {
                    // False - Red channel
                    pixel.r = intensity;
                    pixel.b = intensity / 4;
                } else {
                    // Unassigned - Blue channel
                    pixel.b = intensity;
                    pixel.g = intensity / 4;
                    pixel.r = intensity / 4;
                }
            }
            
            fwrite(&pixel, sizeof(Pixel), 1, fp);
        }
    }
    
    fclose(fp);
    return SAT_SUCCESS;
}

/* ============================================================================
 * Utility Functions
 * ============================================================================ */

void print_assignment(const int* assignment, size_t num_vars) {
    printf("Assignment: ");
    for (size_t i = 1; i <= num_vars; i++) {
        if (assignment[i] != -1) {
            printf("x%zu=%d ", i, assignment[i]);
        }
    }
    printf("\n");
}

void print_cnf(const CNF* cnf) {
    printf("CNF Formula:\n");
    printf("Variables: %zu\n", cnf->num_vars);
    printf("Clauses: %zu\n", cnf->num_clauses);
    
    for (size_t i = 0; i < cnf->num_clauses; i++) {
        printf("  Clause %zu: (", i);
        Clause* clause = &cnf->clauses[i];
        for (size_t j = 0; j < clause->size; j++) {
            if (j > 0) printf(" ∨ ");
            int lit = clause->literals[j].var;
            if (lit < 0) {
                printf("¬x%d", -lit);
            } else {
                printf("x%d", lit);
            }
        }
        printf(")\n");
    }
}

void print_stats(const SATStats* stats) {
    printf("Solver Statistics:\n");
    printf("  Decisions: %zu\n", stats->decisions);
    printf("  Propagations: %zu\n", stats->propagations);
    printf("  Conflicts: %zu\n", stats->conflicts);
    printf("  Learned Clauses: %zu\n", stats->learned_clauses);
    printf("  CPU Time: %.3f seconds\n", stats->cpu_time);
}

/* ============================================================================
 * DIMACS
 * ============================================================================ */

/* Token reader over a FILE* or a string. */
typedef struct {
    FILE* fp;
    const char* str;
} TokenSource;

static int src_getc(TokenSource* src) {
    if (src->fp) return fgetc(src->fp);
    if (!*src->str) return EOF;
    return (unsigned char)*src->str++;
}

/* Parse DIMACS: "c" lines are comments, a line starting with "%" ends the input
 * (SATLIB files), a clause ends at 0 and may span lines, a lone 0 is the empty
 * clause, and a last clause without its 0 is still added. NULL on a missing or bad
 * header, a non-integer token, or an out-of-range literal. */
static CNF* parse_dimacs(TokenSource* src) {
    CNF* cnf = NULL;
    IVec clause = {0};
    char tok[64];
    bool at_line_start = true;
    int ch;
    for (;;) {
        ch = src_getc(src);
        while (ch != EOF && isspace(ch)) {
            if (ch == '\n') at_line_start = true;
            ch = src_getc(src);
        }
        if (ch == EOF) break;
        if (at_line_start && ch == '%') break;  /* SATLIB end marker */
        if (at_line_start && ch == 'c') {
            while (ch != EOF && ch != '\n') ch = src_getc(src);
            continue;
        }
        size_t len = 0;
        while (ch != EOF && !isspace(ch)) {
            if (len + 1 < sizeof(tok)) tok[len++] = (char)ch;
            ch = src_getc(src);
        }
        tok[len] = '\0';
        at_line_start = (ch == '\n');
        if (strcmp(tok, "p") == 0) {
            char fmt[16] = {0};
            long nv = -1, nc = -1;
            char rest[256];
            size_t r = 0;
            while (ch != EOF && ch != '\n') {
                if (r + 1 < sizeof(rest)) rest[r++] = (char)ch;
                ch = src_getc(src);
            }
            rest[r] = '\0';
            at_line_start = true;
            if (cnf || sscanf(rest, "%15s %ld %ld", fmt, &nv, &nc) != 3 || strcmp(fmt, "cnf") != 0 || nv < 0) {
                goto fail;
            }
            cnf = cnf_create((size_t)nv);
            continue;
        }
        if (!cnf) goto fail;
        char* end = NULL;
        long lit = strtol(tok, &end, 10);
        if (*end != '\0' || lit > INT_MAX || lit < -INT_MAX) goto fail;
        if (lit == 0) {
            Clause c = {0};
            Literal* lits = clause.size ? (Literal*)sat_malloc(clause.size * sizeof(Literal)) : NULL;
            for (size_t i = 0; i < clause.size; i++) {
                lits[i].var = clause.data[i];
                lits[i].value = false;
            }
            c.literals = lits;
            c.size = c.capacity = clause.size;
            SATResult ok = cnf_add_clause_array(cnf, &c);
            sat_free(lits);
            if (ok != SAT_SUCCESS) goto fail;
            clause.size = 0;
        } else {
            ivec_push(&clause, (int)lit);
        }
    }
    if (cnf && clause.size) {
        Clause c = {0};
        Literal* lits = (Literal*)sat_malloc(clause.size * sizeof(Literal));
        for (size_t i = 0; i < clause.size; i++) {
            lits[i].var = clause.data[i];
            lits[i].value = false;
        }
        c.literals = lits;
        c.size = c.capacity = clause.size;
        SATResult ok = cnf_add_clause_array(cnf, &c);
        sat_free(lits);
        if (ok != SAT_SUCCESS) goto fail;
    }
    sat_free(clause.data);
    return cnf;
fail:
    sat_free(clause.data);
    cnf_destroy(cnf);
    return NULL;
}

CNF* cnf_parse_dimacs(const char* filename) {
    FILE* fp = fopen(filename, "r");
    if (!fp) return NULL;
    TokenSource src = {fp, NULL};
    CNF* cnf = parse_dimacs(&src);
    fclose(fp);
    return cnf;
}

CNF* cnf_parse_string(const char* cnf_string) {
    if (!cnf_string) return NULL;
    TokenSource src = {NULL, cnf_string};
    return parse_dimacs(&src);
}

SATResult cnf_write_dimacs(const CNF* cnf, const char* filename) {
    if (!cnf || !filename) return SAT_ERROR_INVALID_INPUT;
    FILE* fp = fopen(filename, "w");
    if (!fp) return SAT_ERROR_MEMORY;
    fprintf(fp, "p cnf %zu %zu\n", cnf->num_vars, cnf->num_clauses);
    for (size_t i = 0; i < cnf->num_clauses; i++) {
        for (size_t j = 0; j < cnf->clauses[i].size; j++) fprintf(fp, "%d ", cnf->clauses[i].literals[j].var);
        fprintf(fp, "0\n");
    }
    fclose(fp);
    return SAT_SUCCESS;
}

/* ============================================================================
 * Example program (compile with -DSAT_NO_MAIN to leave it out)
 * ============================================================================ */

#ifndef SAT_NO_MAIN
static const char* result_name(SATResult r) {
    switch (r) {
        case SAT_SUCCESS: return "SATISFIABLE";
        case SAT_UNSATISFIABLE: return "UNSATISFIABLE";
        case SAT_ERROR_TIMEOUT: return "TIMEOUT";
        default: return "ERROR";
    }
}

int main(int argc, char* argv[]) {
    printf("CDCL SAT Solver with PPM Visualization\n");
    printf("======================================\n\n");

    printf("Example 1: Simple SAT problem\n");
    CNF* cnf1 = cnf_create(3);
    int clause1[] = {1, -2};
    int clause2[] = {-1, 2, 3};
    int clause3[] = {-3, 1};
    cnf_add_clause(cnf1, clause1, 2);
    cnf_add_clause(cnf1, clause2, 3);
    cnf_add_clause(cnf1, clause3, 2);
    print_cnf(cnf1);

    int* assignment1 = (int*)calloc(cnf1->num_vars + 1, sizeof(int));
    if (sat_is_satisfiable(cnf1, assignment1)) {
        printf("SATISFIABLE!\n");
        print_assignment(assignment1, cnf1->num_vars);
        SATSolver* solver1 = sat_solver_create(cnf1);
        memcpy(solver1->assignment, assignment1, (cnf1->num_vars + 1) * sizeof(int));
        generate_ppm_visualization(solver1, "sat_example1.ppm");
        generate_clause_heatmap(cnf1, assignment1, "sat_heatmap1.ppm");
        printf("Generated visualizations: sat_example1.ppm, sat_heatmap1.ppm\n");
        sat_solver_destroy(solver1);
    } else {
        printf("UNSATISFIABLE\n");
    }
    print_stats(&cnf1->stats);
    free(assignment1);
    cnf_destroy(cnf1);

    printf("\n\nExample 2: Random 3-SAT problem\n");
    srand((unsigned)time(NULL));
    int num_vars = 20;
    int num_clauses = 80;
    CNF* cnf2 = cnf_create(num_vars);
    for (int i = 0; i < num_clauses; i++) {
        int clause[3];
        for (int j = 0; j < 3; j++) {
            int var = (rand() % num_vars) + 1;
            clause[j] = (rand() % 2) ? var : -var;
        }
        cnf_add_clause(cnf2, clause, 3);
    }
    printf("Generated random 3-SAT: %d variables, %d clauses\n", num_vars, num_clauses);
    SATSolver* solver2 = sat_solver_create_with_config(cnf2, sat_minisat_config());
    SATResult result = sat_solve(solver2);
    printf("%s\n", result_name(result));
    if (result == SAT_SUCCESS) {
        generate_ppm_visualization(solver2, "sat_random.ppm");
        generate_clause_heatmap(cnf2, solver2->assignment, "sat_random_heatmap.ppm");
        generate_variable_activity_map(solver2, "sat_random_activity.ppm");
        printf("Generated visualizations:\n");
        printf("  - sat_random.ppm (clause-variable matrix)\n");
        printf("  - sat_random_heatmap.ppm (clause satisfaction heatmap)\n");
        printf("  - sat_random_activity.ppm (variable activity map)\n");
    }
    print_stats(&cnf2->stats);
    sat_solver_destroy(solver2);
    cnf_destroy(cnf2);

    if (argc > 1) {
        printf("\n\nExample 3: Parsing DIMACS file: %s\n", argv[1]);
        CNF* cnf3 = cnf_parse_dimacs(argv[1]);
        if (cnf3) {
            printf("Parsed CNF: %zu variables, %zu clauses\n", cnf3->num_vars, cnf3->num_clauses);
            SATSolver* solver3 = sat_solver_create(cnf3);
            SATResult result3 = sat_solve(solver3);
            printf("%s\n", result_name(result3));
            if (result3 == SAT_SUCCESS) {
                generate_ppm_visualization(solver3, "sat_dimacs.ppm");
                printf("Generated visualization: sat_dimacs.ppm\n");
            }
            print_stats(&cnf3->stats);
            sat_solver_destroy(solver3);
            cnf_destroy(cnf3);
        } else {
            printf("Failed to parse DIMACS file\n");
        }
    }

    printf("\n\nVisualization Legend:\n");
    printf("  Green: Satisfied literal\n");
    printf("  Red: Unsatisfied literal\n");
    printf("  Blue: Unassigned variable (light=positive, dark=negative)\n");
    printf("  Gray: Learned clause\n");
    return 0;
}
#endif /* SAT_NO_MAIN */
