/*
 * Test driver for SAT.c, used by tests/test_sat_c.py.
 * Build: cc -O2 -DSAT_NO_MAIN -I. SAT.c tests/sat_c_driver.c -o sat_c_driver -lm
 *
 *   sat_c_driver batch MODE RESTART PROOF
 *       stdin: instances, each "p cnf N M" followed by M clauses ending in 0
 *       (an empty clause is a lone 0). MODE is cdcl or dpll, RESTART is the
 *       restart interval, PROOF is 1 to print the DRUP proof.
 *       stdout per instance: proof lines "r <lits> 0" (if PROOF), then
 *       "s SATISFIABLE" + "v <lits> 0", "s UNSATISFIABLE", or "s TIMEOUT".
 *   sat_c_driver string MODE
 *       stdin: one DIMACS text, parsed with cnf_parse_string.
 *   sat_c_driver dimacs MODE PROOF_FILE
 *       stdin: one DIMACS text (read through cnf_parse_dimacs on a temp file);
 *       the DRUP proof is written to PROOF_FILE.
 *   sat_c_driver api
 *       checks of the public API; prints "ok <name>" or "FAIL <name>".
 */
#include "SAT.h"
#include <string.h>

static SATConfig make_config(const char* mode, long restart) {
    SATConfig config = sat_default_config();
    config.use_clause_learning = strcmp(mode, "dpll") != 0;
    config.enable_visualization = false;
    config.max_conflicts = 0;
    if (restart > 0) config.restart_interval = (size_t)restart;
    return config;
}

static void print_result(SATSolver* solver, SATResult r) {
    if (r == SAT_SUCCESS) {
        printf("s SATISFIABLE\nv");
        for (size_t v = 1; v <= solver->cnf->num_vars; v++) {
            printf(" %d", solver->assignment[v] == 1 ? (int)v : -(int)v);
        }
        printf(" 0\n");
    } else if (r == SAT_UNSATISFIABLE) {
        printf("s UNSATISFIABLE\n");
    } else if (r == SAT_ERROR_TIMEOUT) {
        printf("s TIMEOUT\n");
    } else {
        printf("s ERROR %d\n", (int)r);
    }
}

static void copy_proof(FILE* tmp) {
    char line[65536];
    rewind(tmp);
    while (fgets(line, sizeof line, tmp)) printf("r %s", line);
}

static int run_batch(const char* mode, long restart, int proof) {
    char p[8], fmt[8];
    long n, m;
    while (scanf("%7s %7s %ld %ld", p, fmt, &n, &m) == 4) {
        CNF* cnf = cnf_create((size_t)n);
        int* lits = (int*)malloc(((size_t)n * 2 + 1) * sizeof(int) + 64);
        size_t cap = (size_t)n * 2 + 16;
        for (long i = 0; i < m; i++) {
            size_t k = 0;
            int lit;
            while (scanf("%d", &lit) == 1 && lit != 0) {
                if (k == cap) {
                    cap *= 2;
                    lits = (int*)realloc(lits, cap * sizeof(int));
                }
                lits[k++] = lit;
            }
            Clause c;
            Literal* ls = (Literal*)malloc((k ? k : 1) * sizeof(Literal));
            for (size_t j = 0; j < k; j++) {
                ls[j].var = lits[j];
                ls[j].value = false;
            }
            c.literals = ls;
            c.size = c.capacity = k;
            c.learned = false;
            c.activity = 0.0f;
            if (cnf_add_clause_array(cnf, &c) != SAT_SUCCESS) {
                printf("s ERROR input\n");
                free(ls);
                free(lits);
                cnf_destroy(cnf);
                return 1;
            }
            free(ls);
        }
        free(lits);
        SATSolver* solver = sat_solver_create_with_config(cnf, make_config(mode, restart));
        FILE* tmp = NULL;
        if (proof) {
            tmp = tmpfile();
            sat_set_proof_output(solver, tmp);
        }
        SATResult r = sat_solve(solver);
        if (tmp) {
            fflush(tmp);
            copy_proof(tmp);
            fclose(tmp);
        }
        print_result(solver, r);
        sat_solver_destroy(solver);
        cnf_destroy(cnf);
    }
    return 0;
}

static char* read_all(FILE* fp) {
    size_t cap = 4096, len = 0;
    char* buf = (char*)malloc(cap);
    int ch;
    while ((ch = fgetc(fp)) != EOF) {
        if (len + 1 >= cap) buf = (char*)realloc(buf, cap *= 2);
        buf[len++] = (char)ch;
    }
    buf[len] = '\0';
    return buf;
}

static int run_string(const char* mode) {
    char* text = read_all(stdin);
    CNF* cnf = cnf_parse_string(text);
    free(text);
    if (!cnf) {
        printf("s PARSE_ERROR\n");
        return 0;
    }
    SATSolver* solver = sat_solver_create_with_config(cnf, make_config(mode, 0));
    print_result(solver, sat_solve(solver));
    sat_solver_destroy(solver);
    cnf_destroy(cnf);
    return 0;
}

static int run_dimacs(const char* mode, const char* proof_path) {
    char* text = read_all(stdin);
    char path[] = "sat_c_driver_input.cnf";
    FILE* fp = fopen(path, "w");
    if (!fp) return 1;
    fputs(text, fp);
    fclose(fp);
    free(text);
    CNF* cnf = cnf_parse_dimacs(path);
    remove(path);
    if (!cnf) {
        printf("s PARSE_ERROR\n");
        return 0;
    }
    FILE* proof = fopen(proof_path, "w");
    SATSolver* solver = sat_solver_create_with_config(cnf, make_config(mode, 0));
    sat_set_proof_output(solver, proof);
    print_result(solver, sat_solve(solver));
    if (proof) fclose(proof);
    sat_solver_destroy(solver);
    cnf_destroy(cnf);
    return 0;
}

static int failures = 0;
static void check(int cond, const char* name) {
    printf("%s %s\n", cond ? "ok" : "FAIL", name);
    if (!cond) failures++;
}

static int run_api(void) {
    /* cnf_add_clause keeps rejecting empty / NULL clauses and now range-checks. */
    CNF* cnf = cnf_create(3);
    int bad_zero[] = {1, 0};
    int bad_range[] = {4};
    int ok_clause[] = {1, -2};
    check(cnf_add_clause(cnf, ok_clause, 0) == SAT_ERROR_INVALID_INPUT, "add_clause_rejects_size_0");
    check(cnf_add_clause(cnf, NULL, 1) == SAT_ERROR_INVALID_INPUT, "add_clause_rejects_null");
    check(cnf_add_clause(cnf, bad_zero, 2) == SAT_ERROR_INVALID_INPUT, "add_clause_rejects_literal_0");
    check(cnf_add_clause(cnf, bad_range, 1) == SAT_ERROR_INVALID_INPUT, "add_clause_rejects_out_of_range");
    check(cnf->num_clauses == 0, "rejected_clauses_not_added");

    /* (x1 | -x2) (-x1 | x2 | x3) (-x3 | x1): satisfiable */
    int c2[] = {-1, 2, 3}, c3[] = {-3, 1};
    cnf_add_clause(cnf, ok_clause, 2);
    cnf_add_clause(cnf, c2, 3);
    cnf_add_clause(cnf, c3, 2);
    int assignment[4];
    check(sat_is_satisfiable(cnf, assignment), "is_satisfiable");
    check(validate_solution(cnf, assignment) == SAT_SUCCESS, "validate_solution_model");

    /* assumptions: x2 and -x1 contradict (x1 | -x2) */
    SATSolver* solver = sat_solver_create(cnf);
    int assume_bad[] = {2, -1};
    int assume_ok[] = {3};
    check(sat_solve_with_assumptions(solver, assume_bad, 2) == SAT_UNSATISFIABLE, "assumptions_unsat");
    check(sat_solve_with_assumptions(solver, assume_ok, 1) == SAT_SUCCESS && solver->assignment[3] == 1 &&
              solver->assignment[1] == 1, "assumptions_sat");
    check(cnf->num_clauses == 3, "assumptions_leave_cnf_unchanged");
    sat_solver_destroy(solver);

    /* cnf_copy and cnf_simplify */
    CNF* copy = cnf_copy(cnf);
    int taut[] = {2, -2, 1}, dup[] = {3, 3, -1};
    cnf_add_clause(copy, taut, 3);
    cnf_add_clause(copy, dup, 3);
    check(copy->num_clauses == 5 && cnf->num_clauses == 3, "cnf_copy_independent");
    cnf_simplify(copy);
    check(copy->num_clauses == 4 && copy->clauses[3].size == 2, "cnf_simplify");
    cnf_destroy(copy);

    /* empty clause through cnf_add_clause_array makes the formula UNSAT */
    CNF* empty = cnf_create(2);
    Clause e = {NULL, 0, 0, false, 0.0f};
    check(cnf_add_clause_array(empty, &e) == SAT_SUCCESS, "add_clause_array_empty");
    check(!sat_is_satisfiable(empty, NULL), "empty_clause_unsat");
    cnf_destroy(empty);

    /* pigeonhole PHP(5,4) is UNSAT: check CDCL, DPLL, timeout, configs */
    int holes = 4, pigeons = 5;
    CNF* php = cnf_create((size_t)(holes * pigeons));
    for (int p = 0; p < pigeons; p++) {
        int c[4];
        for (int h = 0; h < holes; h++) c[h] = p * holes + h + 1;
        cnf_add_clause(php, c, (size_t)holes);
    }
    for (int h = 0; h < holes; h++)
        for (int p = 0; p < pigeons; p++)
            for (int q = p + 1; q < pigeons; q++) {
                int c[2] = {-(p * holes + h + 1), -(q * holes + h + 1)};
                cnf_add_clause(php, c, 2);
            }
    SATConfig configs[3] = {sat_default_config(), sat_minisat_config(), sat_glucose_config()};
    for (int i = 0; i < 3; i++) {
        SATSolver* s = sat_solver_create_with_config(php, configs[i]);
        check(sat_solve(s) == SAT_UNSATISFIABLE, i == 0 ? "php_default" : i == 1 ? "php_minisat" : "php_glucose");
        sat_solver_destroy(s);
    }
    SATConfig dpll_cfg = sat_default_config();
    dpll_cfg.use_clause_learning = false;
    SATSolver* sd = sat_solver_create_with_config(php, dpll_cfg);
    check(!dpll(sd, 0) && dpll_with_learning(sd) == false, "dpll_wrappers_unsat");
    sat_solver_destroy(sd);
    SATConfig tiny = sat_default_config();
    tiny.max_conflicts = 1;
    SATSolver* st = sat_solver_create_with_config(php, tiny);
    check(sat_solve(st) == SAT_ERROR_TIMEOUT, "max_conflicts_timeout");
    check(sat_solve(st) == SAT_ERROR_TIMEOUT, "solve_twice");
    sat_solver_destroy(st);

    /* analyze_conflict on a hand-made conflict: decide x1 under (-1 | 2) (-1 | -2) */
    CNF* small = cnf_create(2);
    int a1[] = {-1, 2}, a2[] = {-1, -2};
    cnf_add_clause(small, a1, 2);
    cnf_add_clause(small, a2, 2);
    SATSolver* sa = sat_solver_create(small);
    check(sat_solve(sa) == SAT_SUCCESS && sa->assignment[1] == 0, "small_sat");
    backtrack(sa, 0);
    sa->current_level = 1;
    assign_variable(sa, 1, true, -1);
    check(!unit_propagate(sa), "unit_propagate_conflict");
    Clause learned;
    int bt = 99;
    analyze_conflict(sa, &learned, &bt);
    check(learned.size == 1 && learned.literals[0].var == -1 && bt == 0, "analyze_conflict_uip");
    free(learned.literals);
    sat_solver_destroy(sa);
    cnf_destroy(small);

    /* DIMACS round trip */
    check(cnf_write_dimacs(php, "sat_c_api_roundtrip.cnf") == SAT_SUCCESS, "write_dimacs");
    CNF* back = cnf_parse_dimacs("sat_c_api_roundtrip.cnf");
    remove("sat_c_api_roundtrip.cnf");
    check(back && back->num_vars == php->num_vars && back->num_clauses == php->num_clauses, "parse_dimacs_roundtrip");
    if (back) {
        check(!sat_is_satisfiable(back, NULL), "roundtrip_unsat");
        cnf_destroy(back);
    }
    cnf_destroy(php);
    check(cnf_parse_string("p cnf 2 1\n1 3 0\n") == NULL, "parse_rejects_out_of_range");
    check(cnf_parse_string("1 2 0\n") == NULL, "parse_rejects_missing_header");
    CNF* parsed = cnf_parse_string("c comment\np cnf 2 3\n1 2\n0 -1 0\n-2 0\n%\n0\n");
    check(parsed && parsed->num_clauses == 3 && parsed->clauses[0].size == 2, "parse_multiline_clause");
    if (parsed) cnf_destroy(parsed);

    /* pure literals at level 0 */
    CNF* pure = cnf_create(3);
    int p1[] = {1, 2}, p2[] = {1, -2}, p3[] = {-3, 2};
    cnf_add_clause(pure, p1, 2);
    cnf_add_clause(pure, p2, 2);
    cnf_add_clause(pure, p3, 2);
    SATSolver* sp = sat_solver_create(pure);
    check(pure_literal_elimination(sp) && sp->assignment[1] == 1 && sp->assignment[3] == 0, "pure_literals");
    sat_solver_destroy(sp);
    cnf_destroy(pure);

    /* solver destroyed after its CNF: must not touch the CNF */
    CNF* gone = cnf_create(2);
    SATSolver* sg = sat_solver_create(gone);
    watch_clause(sg->watches, 0, 1, -2);
    watch_clause(sg->watches, 1, -2, 2);
    unwatch_clause(sg->watches, 1, -2);
    cnf_destroy(gone);
    sat_solver_destroy(sg);
    check(1, "destroy_after_cnf");

    cnf_destroy(cnf);
    printf("%s\n", failures ? "API FAILED" : "API OK");
    return failures ? 1 : 0;
}

int main(int argc, char** argv) {
    if (argc >= 5 && strcmp(argv[1], "batch") == 0) return run_batch(argv[2], atol(argv[3]), atoi(argv[4]));
    if (argc >= 3 && strcmp(argv[1], "string") == 0) return run_string(argv[2]);
    if (argc >= 4 && strcmp(argv[1], "dimacs") == 0) return run_dimacs(argv[2], argv[3]);
    if (argc >= 2 && strcmp(argv[1], "api") == 0) return run_api();
    fprintf(stderr, "usage: see the comment at the top of tests/sat_c_driver.c\n");
    return 2;
}
