#ifndef PPM_PANDAS_H
#define PPM_PANDAS_H
/*
 *  pandas.h — public bridge API for ppm-panda-lib
 *
 *  These functions delegate to the symbols exported by
 *  pandas_bridge.so (generated from pandas_bridge.pyx).
 *
 *  All return 0 on success, non-zero on failure.
 */

#ifdef __cplusplus
extern "C" {
#endif

/** Install pandas (latest if @version is NULL). */
int panda_install(const char *version);

/** Pre-fetch wheels listed in wheels.lock into ./wheelhouse. */
int panda_cache_wheels(void);

/** Pretty-print a 10-row preview + dtype summary of the CSV at @path. */
int panda_csv_peek(const char *path);

/** Emit environment diagnostics (Python, pandas, NumPy, platform …). */
int panda_doctor(void);

#ifdef __cplusplus
}
#endif
#endif /* PPM_PANDAS_H */
