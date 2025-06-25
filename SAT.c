#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>
#include <string.h>

// Structure for a literal (variable or its negation)
typedef struct {
    int var;  // Variable index (positive for true, negative for negated)
    bool value; // Assigned value (true/false)
} Literal;

// Structure for a clause (disjunction of literals)
typedef struct {
    Literal* literals;
    size_t size;
} Clause;

// Structure for the CNF formula
typedef struct {
    Clause* clauses;
    size_t num_clauses;
    size_t num_vars;
} CNF;

// Forward declarations
bool dpll(CNF* cnf, int* assignment, size_t var_idx);
bool unit_propagate(CNF* cnf, int* assignment);
bool is_satisfiable(CNF* cnf, int* assignment);

// Initialize CNF from a simple array (for demo purposes)
CNF* cnf_init(size_t num_vars, size_t num_clauses, int* clause_data) {
    CNF* cnf = (CNF*)malloc(sizeof(CNF));
    cnf->num_vars = num_vars;
    cnf->num_clauses = num_clauses;
    cnf->clauses = (Clause*)malloc(num_clauses * sizeof(Clause));

    int idx = 0;
    for (size_t i = 0; i < num_clauses; i++) {
        cnf->clauses[i].size = 0;
        while (clause_data[idx] != 0) { // 0 marks end of clause
            cnf->clauses[i].size++;
            idx++;
        }
        idx++; // Skip the 0
        cnf->clauses[i].literals = (Literal*)malloc(cnf->clauses[i].size * sizeof(Literal));
        size_t j = 0;
        while (clause_data[idx] != 0) {
            cnf->clauses[i].literals[j].var = clause_data[idx];
            cnf->clauses[i].literals[j].value = false; // Unassigned
            j++; idx++;
        }
        idx++; // Skip the 0
    }
    return cnf;
}

// Free CNF memory
void cnf_free(CNF* cnf) {
    for (size_t i = 0; i < cnf->num_clauses; i++) {
        free(cnf->clauses[i].literals);
    }
    free(cnf->clauses);
    free(cnf);
}

// Check if a clause is satisfied or empty
bool clause_satisfied(Clause* clause, int* assignment) {
    for (size_t i = 0; i < clause->size; i++) {
        int var = abs(clause->literals[i].var);
        bool sign = clause->literals[i].var > 0;
        if (assignment[var] != -1 && ((assignment[var] == 1) == sign)) {
            return true; // Satisfied
        }
    }
    return false; // Unsatisfied or unassigned
}

// Unit propagation
bool unit_propagate(CNF* cnf, int* assignment) {
    bool changed;
    do {
        changed = false;
        for (size_t i = 0; i < cnf->num_clauses; i++) {
            Clause* clause = &cnf->clauses[i];
            int unassigned = -1, sign = 0;
            bool has_assigned = false;
            for (size_t j = 0; j < clause->size; j++) {
                int var = abs(clause->literals[j].var);
                if (assignment[var] != -1) {
                    has_assigned = true;
                    if (((assignment[var] == 1) == (clause->literals[j].var > 0))) {
                        break; // Clause satisfied
                    }
                } else if (unassigned == -1) {
                    unassigned = var;
                    sign = clause->literals[j].var > 0 ? 1 : 0;
                }
            }
            if (!has_assigned && unassigned != -1) {
                assignment[unassigned] = sign;
                changed = true;
            } else if (has_assigned && !clause_satisfied(clause, assignment)) {
                return false; // Conflict
            }
        }
    } while (changed);
    return true;
}

// DPLL recursive solver
bool dpll(CNF* cnf, int* assignment, size_t var_idx) {
    if (var_idx > cnf->num_vars) {
        return true; // All variables assigned
    }

    if (!unit_propagate(cnf, assignment)) {
        return false; // Conflict after propagation
    }

    bool all_satisfied = true;
    for (size_t i = 0; i < cnf->num_clauses; i++) {
        if (!clause_satisfied(&cnf->clauses[i], assignment)) {
            all_satisfied = false;
            break;
        }
    }
    if (all_satisfied) {
        return true; // Solution found
    }

    int var = var_idx;
    assignment[var] = 0; // Try false
    if (dpll(cnf, assignment, var_idx + 1)) {
        return true;
    }
    assignment[var] = 1; // Try true
    if (dpll(cnf, assignment, var_idx + 1)) {
        return true;
    }
    assignment[var] = -1; // Backtrack
    return false;
}

// Main satisfiability check
bool is_satisfiable(CNF* cnf, int* assignment) {
    for (size_t i = 0; i <= cnf->num_vars; i++) {
        assignment[i] = -1; // Initialize as unassigned
    }
    return dpll(cnf, assignment, 1);
}

int main() {
    // Example: (x1 ∨ ¬x2) ∧ (¬x1 ∨ x2)
    int clause_data[] = {1, -2, 0, -1, 2, 0, 0}; // CNF representation
    CNF* cnf = cnf_init(2, 2, clause_data);
    int assignment[3] = {0}; // Index 0 unused, 1-2 for x1-x2

    if (is_satisfiable(cnf, assignment)) {
        printf("Satisfiable! Assignment: x1=%d, x2=%d\n", assignment[1], assignment[2]);
    } else {
        printf("Unsatisfiable\n");
    }

    cnf_free(cnf);
    return 0;
}
