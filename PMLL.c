#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include "PMLL.h"

// Structure definitions (moved to header)
typedef struct {
    int length;
    int *literals;
} clause_t;

typedef struct {
    int *tree;
    int size;
} memory_silo_t;

typedef struct {
    int num_vars;
    int num_clauses;
    clause_t *clauses;
    int *assignment;
    memory_silo_t *silo;
    int flag;
} pml_t;

// Initialize memory silo with Ouroboros caching
memory_silo_t *init_silo(int size) {
    memory_silo_t *silo = (memory_silo_t *)malloc(sizeof(memory_silo_t));
    silo->size = size;
    silo->tree = (int *)calloc(size * 2, sizeof(int)); // Double size for caching
    return silo;
}

// Update memory silo with recursive cache
void update_silo(memory_silo_t *silo, int var, int value, int depth) {
    if (var < silo->size) {
        silo->tree[var] = value;
        if (depth < log2(silo->size) && var > 0) {
            update_silo(silo, var / 2, value, depth + 1); // Recursive cache
        }
    }
}

// Check for conflicts
int check_conflict(clause_t *clauses, int *assignment, int num_clauses, int num_vars) {
    for (int i = 0; i < num_clauses; i++) {
        int satisfied = 0;
        for (int j = 0; j < clauses[i].length; j++) {
            int lit = clauses[i].literals[j];
            int var = abs(lit) - 1;
            if (var < num_vars && assignment[var] == (lit > 0)) {
                satisfied = 1;
                break;
            }
        }
        if (!satisfied) return 1;
    }
    return 0;
}

// Refine assignments with Ouroboros recursion
void pml_refine(pml_t *pml_ptr, int recursion_level) {
    int n = pml_ptr->num_vars;
    clause_t *clauses = pml_ptr->clauses;
    int *assignment = pml_ptr->assignment;
    memory_silo_t *silo = pml_ptr->silo;

    // Unit Propagation
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
        pml_ptr->flag = 1;
        return;
    }

    assignment[unassigned] = 0;
    if (check_conflict(clauses, assignment, pml_ptr->num_clauses, n)) {
        assignment[unassigned] = 1;
        if (check_conflict(clauses, assignment, pml_ptr->num_clauses, n)) {
            assignment[unassigned] = -1;
            update_silo(silo, unassigned, -1, 0);
            if (recursion_level < log2(n)) {
                pml_refine(pml_ptr, recursion_level + 1); // Ouroboros recursion
            }
        }
    }
    update_silo(silo, unassigned, assignment[unassigned], 0);
}

// Ouroboros-enhanced logic loop
void pml_logic_loop(pml_t *pml_ptr, int max_depth) {
    int max_steps = pml_ptr->num_vars * pml_ptr->num_vars + 
                    2 * pml_ptr->num_vars * log2(pml_ptr->num_vars) + 
                    pml_ptr->num_vars; // phi(n)
    int steps = 0;

    while (steps < max_steps) {
        if (pml_ptr->flag == 1) break;
        pml_refine(pml_ptr, 0); // Start recursion
        steps++;
        if (steps % (max_steps / 10) == 0 && max_depth > 0) {
            pml_logic_loop(pml_ptr, max_depth - 1); // Self-referential loop
        }
    }

    if (steps >= max_steps) {
        printf("Max steps reached, possible unsatisfiable.\n");
        pml_ptr->flag = 1;
    }
}

// PPM output function (grayscale image of assignments)
void output_to_ppm(pml_t *pml_ptr, const char *filename) {
    FILE *fp = fopen(filename, "wb");
    fprintf(fp, "P5\n%d %d\n255\n", pml_ptr->num_vars, 1);
    for (int i = 0; i < pml_ptr->num_vars; i++) {
        unsigned char value = (pml_ptr->assignment[i] == 1) ? 255 : 
                            (pml_ptr->assignment[i] == 0) ? 0 : 128;
        fwrite(&value, sizeof(unsigned char), 1, fp);
    }
    fclose(fp);
}

// Initialize PMLL
pml_t *init_pml(int num_vars, int num_clauses, clause_t *clauses) {
    pml_t *pml = (pml_t *)malloc(sizeof(pml_t));
    pml->num_vars = num_vars;
    pml->num_clauses = num_clauses;
    pml->clauses = clauses;
    pml->assignment = (int *)calloc(num_vars, sizeof(int));
    pml->silo = init_silo(num_vars);
    pml->flag = 0;
    return pml;
}

// Free memory
void free_pml(pml_t *pml) {
    for (int i = 0; i < pml->num_clauses; i++) {
        free(pml->clauses[i].literals);
    }
    free(pml->clauses);
    free(pml->assignment);
    free(pml->silo->tree);
    free(pml->silo);
    free(pml);
}

// Main with ppm output
int main() {
    int num_vars = 3;
    int num_clauses = 2;
    clause_t *clauses = (clause_t *)malloc(num_clauses * sizeof(clause_t));
    clauses[0].length = 3;
    clauses[0].literals = (int *)malloc(3 * sizeof(int));
    clauses[0].literals[0] = 1;  // x1
    clauses[0].literals[1] = -2; // ~x2
    clauses[0].literals[2] = 3;  // x3
    clauses[1].length = 3;
    clauses[1].literals = (int *)malloc(3 * sizeof(int));
    clauses[1].literals[0] = -1; // ~x1
    clauses[1].literals[1] = 2;  // x2
    clauses[1].literals[2] = -3; // ~x3

    pml_t *pml = init_pml(num_vars, num_clauses, clauses);
    pml_logic_loop(pml, (int)log2(num_vars)); // Ouroboros depth
    printf("Solution: ");
    for (int i = 0; i < num_vars; i++) {
        if (pml->assignment[i] == 1) printf("x%d=1 ", i + 1);
        else if (pml->assignment[i] == 0) printf("x%d=0 ", i + 1);
    }
    printf("\n");
    output_to_ppm(pml, "solution.ppm");

    free_pml(pml);
    return 0;
}
