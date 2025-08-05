/*
 *  pandas.c — thin dlopen() shim that forwards to pandas_bridge.so
 *
 *  Build this into the same shared object you load as a PPM plugin.
 */

#include "pandas.h"

#include <dlfcn.h>
#include <stdio.h>
#include <string.h>

typedef int (*pf_char)(const char *);
typedef int (*pf_void)(void);

/* function pointers resolved lazily */
static pf_char cb_install = NULL;
static pf_char cb_csv     = NULL;
static pf_void cb_cache   = NULL;
static pf_void cb_doctor  = NULL;

static int bridge_load(void)
{
    static void *handle = NULL;
    if (handle) return 0;                     /* already loaded */

    handle = dlopen("pandas_bridge.so", RTLD_NOW | RTLD_GLOBAL);
    if (!handle) {
        fprintf(stderr, "ppm-panda-lib: %s\n", dlerror());
        return -1;
    }

    cb_install = (pf_char)dlsym(handle, "panda_install");
    cb_cache   = (pf_void)dlsym(handle, "panda_cache_wheels");
    cb_csv     = (pf_char)dlsym(handle, "panda_csv_peek");
    cb_doctor  = (pf_void)dlsym(handle, "panda_doctor");

    if (!cb_install || !cb_cache || !cb_csv || !cb_doctor) {
        fputs("ppm-panda-lib: missing symbol(s) in pandas_bridge.so\n", stderr);
        return -1;
    }
    return 0;
}

/* ────────────────────────────────────────────────────────── */
/* public wrappers (declared in pandas.h)                     */
/* ────────────────────────────────────────────────────────── */

int panda_install(const char *version)
{
    return bridge_load() ? 1 : cb_install(version);
}

int panda_cache_wheels(void)
{
    return bridge_load() ? 1 : cb_cache();
}

int panda_csv_peek(const char *path)
{
    return bridge_load() ? 1 : cb_csv(path);
}

int panda_doctor(void)
{
    return bridge_load() ? 1 : cb_doctor();
}
