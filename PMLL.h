#ifndef PMLL_H
#define PMLL_H

// Structure definitions
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

// Function prototypes
memory_silo_t *init_silo(int size);
void update_silo(memory_silo_t *silo, int var, int value, int depth);
int check_conflict(clause_t *clauses, int *assignment, int num_clauses, int num_vars);
void pml_refine(pml_t *pml_ptr, int recursion_level);
void pml_logic_loop(pml_t *pml_ptr, int max_depth);
void output_to_ppm(pml_t *pml_ptr, const char *filename);
pml_t *init_pml(int num_vars, int num_clauses, clause_t *clauses);
void free_pml(pml_t *pml);

#endif
