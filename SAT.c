#include "SAT.h"
#include <time.h>
#include <math.h>
#include <assert.h>

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

/* ============================================================================
 * Configuration Management
 * ============================================================================ */

SATConfig sat_default_config(void) {
    SATConfig config = {
        .use_vsids = true,
        .use_phase_saving = true,
        .use_clause_learning = false,
        .var_decay = 0.95,
        .clause_decay = 0.999,
        .restart_interval = 100,
        .max_conflicts = 10000,
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

/* ============================================================================
 * CNF Management
 * ============================================================================ */

CNF* cnf_create(size_t num_vars) {
    CNF* cnf = (CNF*)sat_calloc(1, sizeof(CNF));
    cnf->num_vars = num_vars;
    cnf->clause_capacity = 100;
    cnf->clauses = (Clause*)sat_malloc(cnf->clause_capacity * sizeof(Clause));
    cnf->var_states = (VarState*)sat_calloc(num_vars + 1, sizeof(VarState));
    
    // Initialize var states
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

SATResult cnf_add_clause(CNF* cnf, int* literals, size_t size) {
    if (!cnf || !literals || size == 0) {
        return SAT_ERROR_INVALID_INPUT;
    }
    
    // Expand clause array if needed
    if (cnf->num_clauses >= cnf->clause_capacity) {
        cnf->clause_capacity *= 2;
        cnf->clauses = (Clause*)sat_realloc(cnf->clauses, 
                                           cnf->clause_capacity * sizeof(Clause));
    }
    
    // Create new clause
    Clause* clause = &cnf->clauses[cnf->num_clauses];
    clause->size = size;
    clause->capacity = size;
    clause->literals = (Literal*)sat_malloc(size * sizeof(Literal));
    clause->learned = false;
    clause->activity = 0.0;
    
    // Add literals
    for (size_t i = 0; i < size; i++) {
        clause->literals[i].var = literals[i];
        clause->literals[i].value = false;
        
        // Update var state counts
        int var = abs(literals[i]);
        if (literals[i] > 0) {
            cnf->var_states[var].activity += 0.01; // Initial activity
        }
    }
    
    cnf->num_clauses++;
    return SAT_SUCCESS;
}

/* ============================================================================
 * Watch List Management
 * ============================================================================ */

WatchList* watch_list_create(size_t num_vars) {
    WatchList* watches = (WatchList*)sat_calloc(1, sizeof(WatchList));
    watches->pos_watches = (WatchNode**)sat_calloc(num_vars + 1, sizeof(WatchNode*));
    watches->neg_watches = (WatchNode**)sat_calloc(num_vars + 1, sizeof(WatchNode*));
    return watches;
}

void watch_list_destroy(WatchList* watches) {
    if (!watches) return;
    // Note: In full implementation, would need to free all nodes
    sat_free(watches->pos_watches);
    sat_free(watches->neg_watches);
    sat_free(watches);
}

/* ============================================================================
 * Solver Core
 * ============================================================================ */

SATSolver* sat_solver_create(CNF* cnf) {
    return sat_solver_create_with_config(cnf, sat_default_config());
}

SATSolver* sat_solver_create_with_config(CNF* cnf, SATConfig config) {
    SATSolver* solver = (SATSolver*)sat_calloc(1, sizeof(SATSolver));
    solver->cnf = cnf;
    solver->config = config;
    solver->assignment = (int*)sat_malloc((cnf->num_vars + 1) * sizeof(int));
    solver->trail = (int*)sat_malloc((cnf->num_vars + 1) * sizeof(int));
    solver->decision_level = (int*)sat_calloc(cnf->num_vars + 1, sizeof(int));
    solver->watches = watch_list_create(cnf->num_vars);
    
    // Initialize assignment
    for (size_t i = 0; i <= cnf->num_vars; i++) {
        solver->assignment[i] = -1; // Unassigned
    }
    
    return solver;
}

void sat_solver_destroy(SATSolver* solver) {
    if (!solver) return;
    sat_free(solver->assignment);
    sat_free(solver->trail);
    sat_free(solver->decision_level);
    watch_list_destroy(solver->watches);
    sat_free(solver);
}

/* ============================================================================
 * DPLL Algorithm
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
                return false; // Clause is satisfied
            }
        }
    }
    
    if (unassigned_count == 1 && unit_lit) {
        *unit_lit = unassigned_lit;
        return true;
    }
    
    return false;
}

bool unit_propagate(SATSolver* solver) {
    bool changed;
    do {
        changed = false;
        for (size_t i = 0; i < solver->cnf->num_clauses; i++) {
            Clause* clause = &solver->cnf->clauses[i];
            
            if (is_clause_satisfied(clause, solver->assignment)) {
                continue;
            }
            
            int unit_lit;
            if (is_clause_unit(clause, solver->assignment, &unit_lit)) {
                int var = abs(unit_lit);
                int value = unit_lit > 0 ? 1 : 0;
                
                solver->assignment[var] = value;
                solver->trail[solver->trail_size++] = unit_lit;
                solver->cnf->stats.propagations++;
                changed = true;
            } else {
                // Check for conflict (all literals false)
                bool all_false = true;
                for (size_t j = 0; j < clause->size; j++) {
                    int var = abs(clause->literals[j].var);
                    if (solver->assignment[var] == -1) {
                        all_false = false;
                        break;
                    }
                }
                if (all_false) {
                    return false; // Conflict
                }
            }
        }
    } while (changed);
    
    return true;
}

bool dpll(SATSolver* solver, size_t var_idx) {
    // Unit propagation
    if (!unit_propagate(solver)) {
        return false;
    }
    
    // Check if all clauses are satisfied
    bool all_satisfied = true;
    for (size_t i = 0; i < solver->cnf->num_clauses; i++) {
        if (!is_clause_satisfied(&solver->cnf->clauses[i], solver->assignment)) {
            all_satisfied = false;
            break;
        }
    }
    
    if (all_satisfied) {
        return true;
    }
    
    // Find next unassigned variable
    while (var_idx <= solver->cnf->num_vars && solver->assignment[var_idx] != -1) {
        var_idx++;
    }
    
    if (var_idx > solver->cnf->num_vars) {
        return true; // All variables assigned
    }
    
    // Save state for backtracking
    size_t saved_trail_size = solver->trail_size;
    
    // Try false first
    solver->assignment[var_idx] = 0;
    solver->trail[solver->trail_size++] = -(int)var_idx;
    solver->cnf->stats.decisions++;
    
    if (dpll(solver, var_idx + 1)) {
        return true;
    }
    
    // Backtrack
    while (solver->trail_size > saved_trail_size) {
        int lit = solver->trail[--solver->trail_size];
        int var = abs(lit);
        solver->assignment[var] = -1;
    }
    
    // Try true
    solver->assignment[var_idx] = 1;
    solver->trail[solver->trail_size++] = (int)var_idx;
    solver->cnf->stats.decisions++;
    
    if (dpll(solver, var_idx + 1)) {
        return true;
    }
    
    // Backtrack
    while (solver->trail_size > saved_trail_size) {
        int lit = solver->trail[--solver->trail_size];
        int var = abs(lit);
        solver->assignment[var] = -1;
    }
    
    return false;
}

/* ============================================================================
 * Main Solving Interface
 * ============================================================================ */

SATResult sat_solve(SATSolver* solver) {
    clock_t start = clock();
    
    // Initialize
    solver->trail_size = 0;
    solver->current_level = 0;
    
    // Run DPLL
    bool result = dpll(solver, 1);
    
    // Calculate time
    double cpu_time = ((double)(clock() - start)) / CLOCKS_PER_SEC;
    solver->cnf->stats.cpu_time = cpu_time;
    
    if (result) {
        return SAT_SUCCESS;
    } else {
        return SAT_UNSATISFIABLE;
    }
}

bool sat_is_satisfiable(CNF* cnf, int* assignment) {
    SATSolver* solver = sat_solver_create(cnf);
    SATResult result = sat_solve(solver);
    
    if (result == SAT_SUCCESS) {
        // Copy assignment
        for (size_t i = 0; i <= cnf->num_vars; i++) {
            assignment[i] = solver->assignment[i];
        }
    }
    
    sat_solver_destroy(solver);
    return result == SAT_SUCCESS;
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
 * DIMACS Parser
 * ============================================================================ */

CNF* cnf_parse_dimacs(const char* filename) {
    FILE* fp = fopen(filename, "r");
    if (!fp) {
        return NULL;
    }
    
    CNF* cnf = NULL;
    char line[1024];
    
    while (fgets(line, sizeof(line), fp)) {
        if (line[0] == 'c') {
            continue; // Comment
        } else if (line[0] == 'p') {
            // Problem line
            char format[10];
            int num_vars, num_clauses;
            sscanf(line, "p %s %d %d", format, &num_vars, &num_clauses);
            cnf = cnf_create(num_vars);
        } else if (cnf) {
            // Clause line
            int literals[MAX_LITERALS_PER_CLAUSE];
            int lit_count = 0;
            char* token = strtok(line, " \t\n");
            
            while (token && strcmp(token, "0") != 0) {
                literals[lit_count++] = atoi(token);
                token = strtok(NULL, " \t\n");
            }
            
            if (lit_count > 0) {
                cnf_add_clause(cnf, literals, lit_count);
            }
        }
    }
    
    fclose(fp);
    return cnf;
}

/* ============================================================================
 * Main Example
 * ============================================================================ */

int main(int argc, char* argv[]) {
    printf("Enhanced SAT Solver with PPM Visualization\n");
    printf("==========================================\n\n");
    
    // Example 1: Simple satisfiable formula
    printf("Example 1: Simple SAT problem\n");
    CNF* cnf1 = cnf_create(3);
    int clause1[] = {1, -2};      // x1 ∨ ¬x2
    int clause2[] = {-1, 2, 3};   // ¬x1 ∨ x2 ∨ x3
    int clause3[] = {-3, 1};      // ¬x3 ∨ x1
    
    cnf_add_clause(cnf1, clause1, 2);
    cnf_add_clause(cnf1, clause2, 3);
    cnf_add_clause(cnf1, clause3, 2);
    
    print_cnf(cnf1);
    
    int* assignment1 = (int*)calloc(cnf1->num_vars + 1, sizeof(int));
    if (sat_is_satisfiable(cnf1, assignment1)) {
        printf("SATISFIABLE!\n");
        print_assignment(assignment1, cnf1->num_vars);
        
        // Generate visualization
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
    
    // Example 2: Larger random 3-SAT problem
    printf("\n\nExample 2: Random 3-SAT problem\n");
    srand(time(NULL));
    
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
    
    if (result == SAT_SUCCESS) {
        printf("SATISFIABLE!\n");
        
        // Generate multiple visualizations
        generate_ppm_visualization(solver2, "sat_random.ppm");
        generate_clause_heatmap(cnf2, solver2->assignment, "sat_random_heatmap.ppm");
        generate_variable_activity_map(solver2, "sat_random_activity.ppm");
        
        printf("Generated visualizations:\n");
        printf("  - sat_random.ppm (clause-variable matrix)\n");
        printf("  - sat_random_heatmap.ppm (clause satisfaction heatmap)\n");
        printf("  - sat_random_activity.ppm (variable activity map)\n");
    } else {
        printf("UNSATISFIABLE\n");
    }
    
    print_stats(&cnf2->stats);
    sat_solver_destroy(solver2);
    cnf_destroy(cnf2);
    
    // Example 3: Parse from file if provided
    if (argc > 1) {
        printf("\n\nExample 3: Parsing DIMACS file: %s\n", argv[1]);
        CNF* cnf3 = cnf_parse_dimacs(argv[1]);
        
        if (cnf3) {
            printf("Parsed CNF: %zu variables, %zu clauses\n", 
                   cnf3->num_vars, cnf3->num_clauses);
            
            SATSolver* solver3 = sat_solver_create(cnf3);
            SATResult result3 = sat_solve(solver3);
            
            if (result3 == SAT_SUCCESS) {
                printf("SATISFIABLE!\n");
                generate_ppm_visualization(solver3, "sat_dimacs.ppm");
                printf("Generated visualization: sat_dimacs.ppm\n");
            } else {
                printf("UNSATISFIABLE\n");
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
