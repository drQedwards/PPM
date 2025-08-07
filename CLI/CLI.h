#ifndef PPM_CLI_H
#define PPM_CLI_H

#ifdef __cplusplus
extern "C" {
#endif

/**
 *  Entry point for the ppm command-line interface.
 *  Returns 0 on success, non-zero on error.
 */
int ppm_cli_run(int argc, char **argv);

/**
 *  Import a package (or set of packages) into the local PPM cache.
 *
 *  @param pkg_spec   Either "name"  or "name==version".
 *  @param verbose    Extra progress output if non-zero.
 *
 *  Core ppm must provide  ppm_core_import(const char*, const char*, int);
 */
int ppm_cli_import(const char *pkg_spec, int verbose);

#ifdef __cplusplus
}
#endif
#endif /* PPM_CLI_H */
