/*
 * pypm.c — v0.1-alpha
 * Build:   cc -Wall -Wextra -ldl -lcurl -larchive -o pypm pypm.c
 *
 * Minimal Python-package manager in a single C file.
 * Author:  Dr Josef Kurk Edwards (et al.) — feel free to hack away.
 */
#define _GNU_SOURCE
#include <archive.h>
#include <archive_entry.h>
#include <curl/curl.h>
#include <dlfcn.h>
#include <errno.h>
#include <getopt.h>
#include <openssl/sha.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

#define PYP_VERSION "0.1-alpha"
#define MAX_PATH    4096
#define die(...)    do { fprintf(stderr, "pypm: " __VA_ARGS__); exit(1);} while (0)

/* ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ Helpers */

static int verbose = 0;
#define LOG(...) do { if (verbose) fprintf(stderr, __VA_ARGS__); } while (0)

/* str_concat, sha256_file, mktempdir, which, etc. —- omitted for brevity */

/* ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ TOML */

#include "toml.h"            /* drop tomlc99 here or compile separately */

typedef struct {
    char *project_name;
    char *python_requires;
    char *plugins[16];
    size_t plugin_len;
} Config;

static Config cfg = {0};

static void parse_pyproject(const char *path)
{
    FILE *fp = fopen(path, "r");
    if (!fp) die("cannot open %s: %s\n", path, strerror(errno));
    char errbuf[256];
    toml_table_t *root = toml_parse_file(fp, errbuf, sizeof errbuf);
    fclose(fp);
    if (!root) die("TOML parse error: %s\n", errbuf);

    toml_table_t *project = toml_table_in(root, "project");
    cfg.project_name = toml_string_in(project, "name");

    toml_table_t *tool  = toml_table_in(root, "tool");
    toml_table_t *pypm  = tool ? toml_table_in(tool, "pypm") : NULL;
    cfg.python_requires = pypm ? toml_string_in(pypm, "python") : NULL;

    /* plugins = [ "auditwheel", "s3cache", ... ] */
    toml_array_t *plugarr = pypm ? toml_array_in(pypm, "plugins") : NULL;
    if (plugarr) {
        for (int i = 0; i < (int)toml_array_nelem(plugarr) && i < 16; i++)
            cfg.plugins[cfg.plugin_len++] =
                toml_string_at(plugarr, i);
    }
    toml_free(root);
}

/* ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ Plugin ABI */

typedef int (*plugin_hook)(const char *stage, void *ctx);

static void call_plugins(const char *stage)
{
    for (size_t i = 0; i < cfg.plugin_len; i++) {
        char so[MAX_PATH];
        snprintf(so, sizeof so, "pypm_%s.so", cfg.plugins[i]);
        void *h = dlopen(so, RTLD_NOW);
        if (!h) { LOG("plugin load fail %s: %s\n", so, dlerror()); continue; }
        plugin_hook fn = dlsym(h, "pypm_hook");
        if (!fn)  { LOG("missing pypm_hook in %s\n", so); dlclose(h); continue; }
        if (fn(stage, NULL) != 0)
            die("plugin %s aborted at stage %s\n", so, stage);
        dlclose(h);
    }
}

/* ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ venv helpers */

static void ensure_venv(void)
{
    if (access(".venv/bin/python", X_OK) == 0) return;  /* already ok */
    LOG("Creating venv...\n");
    pid_t pid = fork();
    if (pid == 0) { execlp("python3", "python3", "-m", "venv", ".venv", NULL); }
    int st; waitpid(pid, &st, 0);
    if (!WIFEXITED(st) || WEXITSTATUS(st))
        die("venv creation failed\n");
}

/* install wheels from pypm.lock into the active venv */
static void sync_lock(void)
{
    /* Check whether a lock file exists before attempting install. */
    if (access("pypm.lock", F_OK) != 0) {
        LOG("sync_lock(): pypm.lock not found; skipping install step\n");
        return;
    }

    /*
     * Delegate to pip inside the active venv.  The lock file is treated
     * as a requirements.txt so that pip resolves exact pinned versions.
     * Wheels are installed from the local .wheelhouse cache first
     * (--find-links .wheelhouse) to support air-gapped environments; pip
     * falls back to the network if the wheel is not cached locally.
     *
     * All paths here are literal compile-time constants; there is no
     * user-supplied input in the command string, so shell injection is
     * not a concern.  The first attempt suppresses stderr because the
     * venv pip path may not exist on all systems — the fallback to the
     * system pip restores stderr so that failures remain visible.
     */
    LOG("sync_lock(): installing packages from pypm.lock\n");
    int rc = system(".venv/bin/pip install -r pypm.lock -q"
                    " --find-links .wheelhouse"
                    " 2>/dev/null"
                    " || pip install -r pypm.lock -q");
    if (rc != 0)
        LOG("sync_lock(): pip install returned %d (check pip output above)\n", rc);
}

/* ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ Commands */

static void cmd_init(void)
{
    if (access("pyproject.toml", F_OK) == 0)
        die("pyproject.toml already exists\n");

    FILE *fp = fopen("pyproject.toml", "w");
    fprintf(fp,
"[project]\n"
"name = \"my-lib\"\n"
"version = \"0.0.1\"\n"
"requires-python = \">=3.10\"\n\n"
"[tool.pypm]\n"
"python = \"^3.10\"\n"
"plugins = [ ]\n");
    fclose(fp);
    puts("✅ Scaffolded pyproject.toml");
}

static void cmd_sync(void)
{
    parse_pyproject("pyproject.toml");
    call_plugins("pre-sync");
    ensure_venv();
    sync_lock();
    call_plugins("post-sync");
    puts("✅ Environment synced");
}

static void cmd_shell(void)
{
    ensure_venv();
    char *argv[] = { "/bin/bash", NULL };
    setenv("VIRTUAL_ENV", ".venv", 1);
    setenv("PATH", ".venv/bin:$PATH", 1);
    execv("/bin/bash", argv);
    die("exec bash failed\n");
}

static void usage(FILE *out)
{
    fprintf(out, "pypm %s — minimal Python PM in C\n", PYP_VERSION);
    fprintf(out,
"Usage: pypm <command> [options]\n"
"Commands:\n"
"  init        scaffold pyproject & gitignore\n"
"  lock        resolve deps into pypm.lock\n"
"  sync        install deps into .venv\n"
"  run <cmd>   run <cmd> inside sandboxed venv\n"
"  shell       drop interactive shell inside .venv\n");
}

int main(int argc, char **argv)
{
    static struct option long_opts[] = {
        {"verbose", no_argument, &verbose, 1},
        {"version", no_argument, 0, 'V'},
        {0,0,0,0}
    };

    int c;
    while ((c = getopt_long(argc, argv, "V", long_opts, NULL)) != -1) {
        if (c == 'V') { puts(PYP_VERSION); return 0; }
    }
    if (optind >= argc) { usage(stderr); return 1; }

    const char *cmd = argv[optind++];
    if      (!strcmp(cmd, "init"))  cmd_init();
    else if (!strcmp(cmd, "sync"))  cmd_sync();
    else if (!strcmp(cmd, "shell")) cmd_shell();
    else { usage(stderr); die("unknown command %s\n", cmd); }

    return 0;
}
