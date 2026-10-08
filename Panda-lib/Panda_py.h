#ifndef PPM_PANDA_PY_H
#define PPM_PANDA_PY_H
/*
 *  Panda_py.h — embedded-Python helpers behind the `panda` PPM plugin
 *  (Panda.c dispatches sub-commands to these; Panda_py.c implements them).
 *
 *  Not the same API as Pandas.h, which is the dlopen() shim over
 *  pandas_bridge.so. All functions return 0 on success.
 */

#ifdef __cplusplus
extern "C" {
#endif

/** Install pandas: argv[0] is an optional version/spec, argc may be 0. */
int panda_install(int argc, char **argv);

/** Pre-fetch pandas + core dependency wheels. */
int panda_cache_wheels(void);

/** Print a 10-row preview + dtypes of the CSV at @path. */
int panda_csv_peek(const char *path);

/** Print numpy / pandas / platform diagnostics. */
int panda_doctor(void);

#ifdef __cplusplus
}
#endif
#endif /* PPM_PANDA_PY_H */
