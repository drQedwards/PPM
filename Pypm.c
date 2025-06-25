/*  pypm.c  – front-door for PyPM 0.3.x
 *
 *  SPDX-License-Identifier: MIT
 *
 *  Build:  see README or top-level Makefile
 *  Notes:
 *    • Only top-level dispatch lives here.
 *    • Heavy lifting lives in module source files.
 */

#define _GNU_SOURCE
#include <stdio.h>
#include <string.h>
#include "pypm.h"          /* shared interface */

/* ---------------------------------------------------------------------------
 * Forward declarations (implemented in their respective modules)
 * ------------------------------------------------------------------------- */
int cmd_doctor(int, char **);
int cmd_sandbox(int, char **);
int cmd_plugin (int, char **);
int cmd_pypylock(int, char **);
int cmd_version(int, char **);
int cmd_getreqs(int, char **);
int cmd_setup  (int, char **);
int cmd_lock   (int, char **);   /* lock diff / sync */

/* ---------------------------------------------------------------------------
 * Usage helper
 * ------------------------------------------------------------------------- */
static void usage(void)
{
    puts("pypm " PYP_VERSION
         "\nUSAGE: pypm <command> [options]\n"
         "\nCore commands:\n"
         "  doctor                 Diagnose build environment\n"
         "  sandbox [-d DIR]       Spawn isolated shell\n"
         "  plugin  <subcmd> ...   Manage or run plugins\n"
         "  pypylock [-o FILE]     Produce hermetic archive\n"
         "  lock    <subcmd> ...   Lockfile operations (diff, sync)\n"
         "  getreqs                Export requirements.txt from venv\n"
         "  setup   [--python X]   Local dev install from metadata\n"
         "  version                Print PyPM version\n"
         "  help                   Show this help\n");
}

/* ---------------------------------------------------------------------------
 * main()
 * ------------------------------------------------------------------------- */
int main(int argc, char **argv)
{
    if (argc < 2) { usage(); return 1; }

    const char *cmd = argv[1];

    /* Fast path for most-used commands in alphabetical order */
    if (!strcmp(cmd, "doctor"))   return cmd_doctor(argc-1, argv+1);
    if (!strcmp(cmd, "getreqs"))  return cmd_getreqs(argc-1, argv+1);
    if (!strcmp(cmd, "lock"))     return cmd_lock  (argc-1, argv+1);
    if (!strcmp(cmd, "plugin"))   return cmd_plugin(argc-1, argv+1);
    if (!strcmp(cmd, "pypylock")) return cmd_pypylock(argc-1, argv+1);
    if (!strcmp(cmd, "sandbox"))  return cmd_sandbox(argc-1, argv+1);
    if (!strcmp(cmd, "setup"))    return cmd_setup (argc-1, argv+1);
    if (!strcmp(cmd, "version"))  return cmd_version(argc-1, argv+1);

    /* Help aliases */
    if (!strcmp(cmd, "help") || !strcmp(cmd, "-h") || !strcmp(cmd, "--help")) {
        usage();
        return 0;
    }

    fprintf(stderr, "pypm: unknown command \"%s\"\n", cmd);
    usage();
    return 1;
}
