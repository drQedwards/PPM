#include <stdio.h>
#include <stdlib.h>
#include "panda_py.h"

/* mandatory symbol — PPM looks this up with dlsym */
int pypm_plugin_main(int argc, char **argv) {
    if (argc < 2) {
        fputs("usage: panda <install|wheel-cache|csv-peek|doctor> …\n", stderr);
        return 1;
    }

    const char *cmd = argv[1];

    if (!strcmp(cmd, "install")) {
        return panda_install(argc - 2, argv + 2);   // see panda_py.c
    } else if (!strcmp(cmd, "wheel-cache")) {
        return panda_cache_wheels();
    } else if (!strcmp(cmd, "csv-peek")) {
        if (argc < 3) { fputs("csv-peek needs a path\n", stderr); return 2; }
        return panda_csv_peek(argv[2]);
    } else if (!strcmp(cmd, "doctor")) {
        return panda_doctor();
    }

    fprintf(stderr, "unknown sub-command: %s\n", cmd);
    return 3;
}
