#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <getopt.h>
#include "ppm_core.h"   /* <- your existing core symbols */
#include "CLI.h"

/* ---------- helpers -------------------------------------------------- */

static int split_spec(const char *spec, char **name, char **ver) {
    char *eq = strstr(spec, "==");
    if (!eq) { *name = strdup(spec); *ver = NULL; }
    else {
        *name = strndup(spec, eq - spec);
        *ver  = strdup(eq + 2);
    }
    return 0;
}

int ppm_cli_import(const char *pkg_spec, int verbose) {
    char *name = NULL, *ver = NULL;
    split_spec(pkg_spec, &name, &ver);
    int rc = ppm_core_import(name, ver, verbose);
    free(name); free(ver);
    return rc;
}

/* ---------- main driver ---------------------------------------------- */

int ppm_cli_run(int argc, char **argv) {
    const struct option long_opts[] = {
        {"help",    no_argument,       0, 'h'},
        {"verbose", no_argument,       0, 'v'},
        {"from",    required_argument, 0, 'f'}, /* scan a .py file for imports */
        {0,0,0,0}
    };

    int  verbose = 0;
    char *scan_file = NULL;
    int  opt, idx;
    while ((opt = getopt_long(argc, argv, "hvf:", long_opts, &idx)) != -1) {
        switch (opt) {
            case 'v': verbose = 1; break;
            case 'f': scan_file = optarg; break;
            case 'h':
            default :
                puts("Usage: ppm import [options] [pkg1==v pkg2 …]\n"
                     "  -f, --from <script.py>  auto-import deps from a Python file\n"
                     "  -v, --verbose           chatty output");
                return 0;
        }
    }

    /* --- mode 1: scan a .py file ------------------------------------ */
    if (scan_file) {
        /* Very light heuristic: call out to ppm_core_scan_file() that
           returns a newline-separated list of module specs              */
        char **pkgs = NULL;
        size_t n    = ppm_core_scan_file(scan_file, &pkgs);
        for (size_t i = 0; i < n; ++i)
            ppm_cli_import(pkgs[i], verbose);
        ppm_core_free_pkg_list(pkgs, n);
        return 0;
    }

    /* --- mode 2: explicit spec(s) ----------------------------------- */
    for (int i = optind; i < argc; ++i)
        ppm_cli_import(argv[i], verbose);

    if (optind == argc)
        fprintf(stderr, "ppm: nothing to import. See --help.\n");

    return 0;
}
