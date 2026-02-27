/*  pypm.c  —  v0.0.3-dev  (integrated)
 *
 *  Build:    cc -Wall -Wextra -ldl -lcurl -o pypm pypm.c
 *  Run:      ./pypm <command> [options]
 *
 *  Highlights
 *  ────────────────────────────────────────────────────────────────────────────
 *   • getopt_long CLI (in-libc) with sub-command + flag parsing
 *   • Workspace discovery  (env-override + upward search)
 *   • Doctor  v2           (returns #issues as exit-code)
 *   • Sandbox v2           (custom dir or mkdtemp)
 *   • Plugin  v1           (add / run, robust dlopen & curl)
 *   • Hermetic “pypylock”  (tar.gz placeholder, -o <file>)
 *
 *  External deps are minimal (libcurl + libdl + tar|libarchive).
 *  Windows support will require dlopen/dir/temp shims in a later patch.
 */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <getopt.h>
#include <dlfcn.h>
#include <sys/stat.h>
#include <unistd.h>
#include <curl/curl.h>
#include <errno.h>

#define PYP_VERSION  "0.0.3-dev"
#define MAX_PATH     4096

/* ─── Helpers ─────────────────────────────────────────────────────────────── */
static void fatal(const char *msg)
{
    perror(msg);
    exit(EXIT_FAILURE);
}

static int file_exists(const char *p)
{
    struct stat st;
    return stat(p, &st) == 0;
}

/* ─── Workspace ───────────────────────────────────────────────────────────── */
static char *find_workspace_root(void)
{
    static char buf[MAX_PATH];
    const char *env_root = getenv("PYP_WORKSPACE_ROOT");
    if (env_root) {
        snprintf(buf, sizeof(buf), "%s", env_root);
        char probe[MAX_PATH];
        snprintf(probe, sizeof(probe), "%s/pypm-workspace.toml", buf);
        return file_exists(probe) ? buf : NULL;
    }

    if (!getcwd(buf, sizeof(buf))) fatal("getcwd");
    for (char *p = buf; p && *p; ) {
        char probe[MAX_PATH];
        snprintf(probe, sizeof(probe), "%s/pypm-workspace.toml", p);
        if (file_exists(probe)) return p;
        p = strrchr(p, '/');
        if (p) *p = '\0';
    }
    return NULL;
}

/* ─── Doctor ──────────────────────────────────────────────────────────────── */
static int run_doctor(void)
{
    puts("🔍  pypm doctor — beginning diagnostics");
    int issues = 0;

    /* Python dev headers */
    if (!system("python3 - <<'PY'\n"
                "import sysconfig, sys; "
                "sys.exit(0 if sysconfig.get_config_var('INCLUDEPY') else 1)\n"
                "PY"))
        puts("✅  Python dev headers found");
    else {
        puts("❌  Missing python<ver>-dev / -headers");
        issues++;
    }

    /* C compiler */
    if (!system("cc --version >/dev/null 2>&1"))
        puts("✅  C compiler available");
    else {
        puts("❌  No C compiler in PATH");
        issues++;
    }

    /* TODO: OpenSSL, Rust, WASI, network tests … */

    printf("🏁  Diagnostics complete (%d issue%s found)\n",
           issues, issues == 1 ? "" : "s");
    return issues;                 /* CI can `[[ $? -eq 0 ]]` */
}

/* ─── Sandbox ─────────────────────────────────────────────────────────────── */
static int run_sandbox(const char *custom_dir)
{
    char template[] = "/tmp/pypm-sandbox-XXXXXX";
    char *dir = custom_dir ? (char *)custom_dir : mkdtemp(template);
    if (!dir) fatal("mkdtemp / invalid dir");

    printf("🐚  Spawning shell in %s\n", dir);
    if (chdir(dir) != 0) fatal("chdir");

    char *shell = getenv("SHELL") ? getenv("SHELL") : "/bin/bash";
    execvp(shell, (char *const[]){shell, "-l", NULL});
    fatal("execvp");               /* only if exec fails */
    return 0;
}

/* ─── Plugin subsystem ────────────────────────────────────────────────────── */
typedef int (*plugin_main_f)(int, char **);

static int load_and_run_plugin(const char *name, int argc, char **argv)
{
    char so_path[MAX_PATH];
    const char *home = getenv("HOME") ? getenv("HOME") : ".";
    snprintf(so_path, sizeof(so_path), "%s/.pypm/plugins/%s.so", home, name);

    void *h = dlopen(so_path, RTLD_LAZY);
    if (!h) { fprintf(stderr, "dlopen failed: %s\n", dlerror()); return 1; }

    plugin_main_f entry = (plugin_main_f)dlsym(h, "pypm_plugin_main");
    if (!entry) { fprintf(stderr, "symbol not found in %s\n", name); dlclose(h); return 1; }

    int rc = entry(argc, argv);
    dlclose(h);
    return rc;
}

static int plugin_cmd_add(const char *name, const char *src)
{
    const char *home = getenv("HOME") ? getenv("HOME") : ".";
    char plugin_dir[MAX_PATH];
    snprintf(plugin_dir, sizeof(plugin_dir), "%s/.pypm/plugins", home);
    if (!file_exists(plugin_dir) && mkdir(plugin_dir, 0755) && errno != EEXIST)
        fatal("mkdir ~/.pypm/plugins");

    char dst[MAX_PATH];
    snprintf(dst, sizeof(dst), "%s/%s.so", plugin_dir, name);

    printf("🔌  Downloading plugin %s → %s\n", name, dst);
    CURL *curl = curl_easy_init();
    if (!curl) fatal("curl_easy_init");
    FILE *out = fopen(dst, "wb");
    if (!out) { curl_easy_cleanup(curl); fatal("fopen dst"); }

    curl_easy_setopt(curl, CURLOPT_URL, src);
    curl_easy_setopt(curl, CURLOPT_FAILONERROR, 1L);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, out);

    CURLcode res = curl_easy_perform(curl);
    curl_easy_cleanup(curl);
    fclose(out);

    if (res != CURLE_OK) {
        unlink(dst);
        fprintf(stderr, "Download failed: %s\n", curl_easy_strerror(res));
        return 1;
    }
    puts("✅  Plugin installed");
    return 0;
}

/* ─── Hermetic bundle (“pypylock”) ────────────────────────────────────────── */
static int run_pypylock(const char *out)
{
    printf("📦  Creating hermetic bundle %s\n", out);
    char cmd[MAX_PATH + 64];
    snprintf(cmd, sizeof(cmd), "tar czf %s .venv", out);
    if (system(cmd) == 0) {
        puts("✅  Bundle created");
        return 0;
    }
    puts("❌  Bundle creation failed");
    return 1;
}

/* ─── Usage ──────────────────────────────────────────────────────────────── */
static void usage(void)
{
    puts("pypm " PYP_VERSION
         "\nUSAGE: pypm <command> [options]\n"
         "\nCommands:\n"
         "  doctor                   Diagnose build environment\n"
         "  sandbox [-d DIR]         Spawn isolated shell (default: mkdtemp)\n"
         "  plugin add  NAME SRC     Install plugin from URL/path\n"
         "  plugin run  NAME [ARGS]  Execute plugin with argv\n"
         "  pypylock [-o FILE]       Produce hermetic tar.gz (default dist/venv.tar.gz)\n"
         "  version                  Print pypm CLI version\n"
         "  help                     This message\n"
         "\nEnv:\n"
         "  PYP_WORKSPACE_ROOT       Override workspace detection\n");
}

/* ─── Main ───────────────────────────────────────────────────────────────── */
int main(int argc, char **argv)
{
    if (argc < 2) { usage(); return 1; }

    char *ws = find_workspace_root();
    if (ws)
        printf("🗄️  Workspace root: %s\n", ws);

    const char *cmd = argv[1];

    /*------------- doctor --------------------------------------------------*/
    if (!strcmp(cmd, "doctor"))
        return run_doctor();

    /*------------- sandbox -------------------------------------------------*/
    if (!strcmp(cmd, "sandbox")) {
        const char *dir = NULL;
        int opt;
        /* shift argv by one so getopt only sees sandbox flags */
        optind = 2;
        while ((opt = getopt(argc, argv, "d:")) != -1) {
            if (opt == 'd') dir = optarg;
            else { usage(); return 1; }
        }
        return run_sandbox(dir);
    }

    /*------------- plugin --------------------------------------------------*/
    if (!strcmp(cmd, "plugin")) {
        if (argc < 3) { usage(); return 1; }
        const char *sub = argv[2];
        if (!strcmp(sub, "add") && argc == 5)
            return plugin_cmd_add(argv[3], argv[4]);
        if (!strcmp(sub, "run") && argc >= 4)
            return load_and_run_plugin(argv[3], argc - 3, argv + 3);
        usage();
        return 1;
    }

    /*------------- pypylock -----------------------------------------------*/
    if (!strcmp(cmd, "pypylock")) {
        const char *out = "dist/venv.tar.gz";
        optind = 2;
        int opt;
        while ((opt = getopt(argc, argv, "o:")) != -1) {
            if (opt == 'o') out = optarg;
            else { usage(); return 1; }
        }
        return run_pypylock(out);
    }

    /*------------- version / help -----------------------------------------*/
    if (!strcmp(cmd, "version")) { puts(PYP_VERSION); return 0; }
    if (!strcmp(cmd, "help") || !strcmp(cmd, "--help") || !strcmp(cmd, "-h")) {
        usage();
        return 0;
    }

    fprintf(stderr, "Unknown command: %s\n", cmd);
    usage();
    return 1;
}
