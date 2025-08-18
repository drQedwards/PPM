#ifndef SAT_H
#define SAT_H

#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>
#include <string.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Maximum limits for static allocation options */
#define MAX_VARS 1000
#define MAX_CLAUSES 10000
#define MAX_LITERALS_PER_CLAUSE 100

/* Error codes */
typedef enum {
    SAT_SUCCESS = 0,
    SAT_UNSATISFIABLE = -1,
    SAT_ERROR_MEMORY = -2,
    SAT_ERROR_INVALID_INPUT = -3,
    SAT_ERROR_TIMEOUT = -4
} SATResult;

/* Statistics structure for solver performance */
typedef struct {
    size_t decisions;
    size_t propagations;
    size_t conflicts;
    size_t learned_clauses;
    double cpu_time;
} SATStats;

/* Literal representation */
typedef struct {
    int var;        /* Variable index (positive for true, negative for negated) */
    bool value;     /* Assigned value (true/false) */
} Literal;

/* Clause structure (disjunction of literals) */
typedef struct {
    Literal* literals;
    size_t size;
    size_t capacity;
    bool learned;   /* Flag for learned clauses */
    float activity; /* Activity score for clause deletion */
} Clause;

/* Variable state for advanced heuristics */
typedef struct {
    double activity;    /* VSIDS activity score */
    int decision_level; /* Decision level when assigned */
    int antecedent;     /* Clause that implied this assignment */
    bool phase_saving;  /* Saved phase for restarts */
} VarState;

/* CNF formula structure */
typedef struct {
    Clause* clauses;
    size_t num_clauses;
    size_t clause_capacity;
    size_t num_vars;
    VarState* var_states;
    SATStats stats;
} CNF;

/* Watch list for two-watched literals optimization */
typedef struct WatchNode {
    size_t clause_idx;
    struct WatchNode* next;
} WatchNode;

typedef struct {
    WatchNode** pos_watches; /* Positive literal watches */
    WatchNode** neg_watches; /* Negative literal watches */
} WatchList;

/* Solver configuration */
typedef struct {
    bool use_vsids;          /* Variable State Independent Decaying Sum */
    bool use_phase_saving;   /* Phase saving for restarts */
    bool use_clause_learning;/* Conflict-driven clause learning */
    double var_decay;        /* Variable activity decay factor */
    double clause_decay;     /* Clause activity decay factor */
    size_t restart_interval; /* Conflicts before restart */
    size_t max_conflicts;    /* Maximum conflicts before timeout */
    bool enable_visualization; /* Enable PPM visualization output */
} SATConfig;

/* Main solver structure */
typedef struct {
    CNF* cnf;
    int* assignment;        /* Current variable assignment (-1: unassigned, 0: false, 1: true) */
    int* trail;            /* Assignment trail for backtracking */
    size_t trail_size;
    int* decision_level;   /* Decision level for each variable */
    int current_level;
    WatchList* watches;
    SATConfig config;
    void* user_data;       /* User-defined data pointer */
} SATSolver;

/* CNF Management Functions */
CNF* cnf_create(size_t num_vars);
void cnf_destroy(CNF* cnf);
SATResult cnf_add_clause(CNF* cnf, int* literals, size_t size);
SATResult cnf_add_clause_array(CNF* cnf, Clause* clause);
CNF* cnf_copy(const CNF* original);
SATResult cnf_simplify(CNF* cnf);

/* Parser Functions */
CNF* cnf_parse_dimacs(const char* filename);
CNF* cnf_parse_string(const char* cnf_string);
SATResult cnf_write_dimacs(const CNF* cnf, const char* filename);

/* Solver Functions */
SATSolver* sat_solver_create(CNF* cnf);
SATSolver* sat_solver_create_with_config(CNF* cnf, SATConfig config);
void sat_solver_destroy(SATSolver* solver);
SATResult sat_solve(SATSolver* solver);
SATResult sat_solve_with_assumptions(SATSolver* solver, int* assumptions, size_t num_assumptions);
bool sat_is_satisfiable(CNF* cnf, int* assignment);

/* Core DPLL Functions */
bool dpll(SATSolver* solver, size_t var_idx);
bool dpll_with_learning(SATSolver* solver);
bool unit_propagate(SATSolver* solver);
bool pure_literal_elimination(SATSolver* solver);

/* Advanced Techniques */
void analyze_conflict(SATSolver* solver, Clause* learned_clause, int* backtrack_level);
void restart(SATSolver* solver);
void decay_activities(SATSolver* solver);
int choose_branching_variable(SATSolver* solver);
void update_vsids(SATSolver* solver, int var);

/* Watch List Management */
WatchList* watch_list_create(size_t num_vars);
void watch_list_destroy(WatchList* watches);
void watch_clause(WatchList* watches, size_t clause_idx, int lit1, int lit2);
void unwatch_clause(WatchList* watches, size_t clause_idx, int lit);

/* Assignment Management */
void assign_variable(SATSolver* solver, int var, bool value, int antecedent);
void unassign_variable(SATSolver* solver, int var);
void backtrack(SATSolver* solver, int level);
bool is_clause_satisfied(const Clause* clause, const int* assignment);
bool is_clause_unit(const Clause* clause, const int* assignment, int* unit_lit);

/* Utility Functions */
void print_assignment(const int* assignment, size_t num_vars);
void print_cnf(const CNF* cnf);
void print_stats(const SATStats* stats);
SATResult validate_solution(const CNF* cnf, const int* assignment);
double get_cpu_time(void);

/* Visualization Functions */
SATResult generate_ppm_visualization(const SATSolver* solver, const char* filename);
SATResult generate_clause_heatmap(const CNF* cnf, const int* assignment, const char* filename);
SATResult generate_variable_activity_map(const SATSolver* solver, const char* filename);
SATResult generate_implication_graph(const SATSolver* solver, const char* filename);

/* Memory Management Helpers */
void* sat_malloc(size_t size);
void* sat_calloc(size_t count, size_t size);
void* sat_realloc(void* ptr, size_t new_size);
void sat_free(void* ptr);

/* Default Configuration */
SATConfig sat_default_config(void);
SATConfig sat_minisat_config(void);
SATConfig sat_glucose_config(void);

#ifdef __cplusplus
}
#endif

#endif /* SAT_H */
