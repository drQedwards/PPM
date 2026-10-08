/* Test driver for PMLL.c (built with -DPMLL_NO_MAIN by tests/test_pmll_c.py).
 * Reads instances from stdin: "p cnf N M", then M clauses. A clause is either
 * DIMACS literals ending in 0, or "x LEN v1 ... vLEN" with raw values (this
 * form can carry 0 and INT_MIN as literals, to test that they are ignored).
 * For each instance writes one line to stderr: "R <flag> <a1> ... <aN>".
 * (PMLL's own status messages go to stdout.) */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "PMLL.h"

int main(void)
{
    char tag[8];
    while (scanf("%7s", tag) == 1) {
        int n, m;
        if (strcmp(tag, "p") != 0) return 2;
        if (scanf("%*s %d %d", &n, &m) != 2) return 2;
        clause_t *clauses = (clause_t *)calloc((size_t)(m > 0 ? m : 1), sizeof(clause_t));
        if (!clauses) return 3;
        for (int i = 0; i < m; i++) {
            char first[32];
            if (scanf("%31s", first) != 1) return 2;
            if (strcmp(first, "x") == 0) {
                int len;
                if (scanf("%d", &len) != 1) return 2;
                clauses[i].length = len;
                clauses[i].literals = (int *)malloc((size_t)(len > 0 ? len : 1) * sizeof(int));
                for (int j = 0; j < len; j++) {
                    long v;
                    if (scanf("%ld", &v) != 1) return 2;
                    clauses[i].literals[j] = (int)v;
                }
                continue;
            }
            int cap = 8, len = 0;
            int *lits = (int *)malloc((size_t)cap * sizeof(int));
            long v = strtol(first, NULL, 10);
            while (v != 0) {
                if (len == cap) {
                    cap *= 2;
                    lits = (int *)realloc(lits, (size_t)cap * sizeof(int));
                }
                lits[len++] = (int)v;
                if (scanf("%ld", &v) != 1) return 2;
            }
            clauses[i].length = len;
            clauses[i].literals = lits;
        }
        pml_t *pml = init_pml(n, m, clauses);
        if (!pml) return 3;
        pml_logic_loop(pml, 0);
        fprintf(stderr, "R %d", pml->flag);
        for (int i = 0; i < n; i++) fprintf(stderr, " %d", pml->assignment[i]);
        fprintf(stderr, "\n");
        free_pml(pml);
    }
    return 0;
}
