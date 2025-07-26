#define _POSIX_C_SOURCE 200809L
#include "importresolver.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>

#ifdef _WIN32
#  include <direct.h>
#  include <process.h>
#else
#  include <sys/wait.h>
#endif

/* -------------------- utilities -------------------- */

static int make_dir_p(const char *path) {
#ifdef _WIN32
    /* very small: assume single component for MVP; refine as needed */
    if (_mkdir(path) == 0 || errno == EEXIST) return 0;
    return errno;
#else
    char cmd[4096];
    snprintf(cmd, sizeof(cmd), "mkdir -p \"%s\"", path);
    int rc = system(cmd);
    if (rc == -1) return -1;
    return WEXITSTATUS(rc);
#endif
}

static char *shell_quote(const char *s) {
    size_t n = strlen(s);
    size_t cap = n * 4 + 16;
    char *out = (char *)malloc(cap);
    if (!out) return NULL;
    size_t j = 0;
    out[j++] = '\'';
    for (size_t i = 0; i < n; ++i) {
        if (s[i] == '\'') {
            const char *esc = "'\"'\"'";
            for (const char *p = esc; *p; ++p) out[j++] = *p;
        } else {
            out[j++] = s[i];
        }
    }
    out[j++] = '\'';
    out[j] = 0;
    return out;
}

/* -------------------- high-level helper path -------------------- */

int ir_resolve_with_helper(const char *root,
                           const char **reqs, size_t n_reqs,
                           const char *index_url,
                           const char *extra_index_url,
                           const char *py_exec,
                           const char *helper_path)
{
    if (!root || !reqs || n_reqs == 0 || !helper_path) {
        fprintf(stderr, "[ir] invalid arguments\n");
        return 2;
    }
    if (!py_exec) py_exec = "python3";
    if (!index_url) index_url = "https://pypi.org/simple";

    char ppm[4096];
    snprintf(ppm, sizeof(ppm), "%s/.ppm", root);
    if (make_dir_p(ppm) != 0) {
        fprintf(stderr, "[ir] failed to create %s: %s\n", ppm, strerror(errno));
        return 3;
    }

    char *q_root   = shell_quote(root);
    char *q_helper = shell_quote(helper_path);
    char *q_index  = shell_quote(index_url);
    char *q_extra  = NULL;
    if (extra_index_url && extra_index_url[0])
        q_extra = shell_quote(extra_index_url);
    if (!q_root || !q_helper || !q_index || (extra_index_url && !q_extra)) {
        fprintf(stderr, "[ir] OOM\n");
        free(q_root); free(q_helper); free(q_index); free(q_extra);
        return 4;
    }

    size_t cap = 65536;
    char *cmd = (char *)malloc(cap);
    if (!cmd) {
        fprintf(stderr, "[ir] OOM\n");
        free(q_root); free(q_helper); free(q_index); free(q_extra);
        return 5;
    }

    int w = snprintf(cmd, cap, "%s %s --root %s --index %s",
                     py_exec, q_helper, q_root, q_index);
    if (w < 0 || (size_t)w >= cap) { free(cmd); return 6; }

    if (q_extra) {
        int w2 = snprintf(cmd + w, cap - w, " --extra-index %s", q_extra);
        if (w2 < 0 || (size_t)w2 >= cap - w) { free(cmd); return 7; }
        w += w2;
    }

    for (size_t i = 0; i < n_reqs; ++i) {
        char *q = shell_quote(reqs[i]);
        if (!q) { free(cmd); return 8; }
        int w3 = snprintf(cmd + w, cap - w, " %s", q);
        free(q);
        if (w3 < 0 || (size_t)w3 >= cap - w) { free(cmd); return 9; }
        w += w3;
    }

    fprintf(stderr, "[ir] run: %s\n", cmd);
    int rc = system(cmd);
    if (rc == -1) {
        fprintf(stderr, "[ir] system() failed\n");
        free(cmd); free(q_root); free(q_helper); free(q_index); free(q_extra);
        return 10;
    }
#ifdef _WIN32
    int exitcode = rc; /* _spawn returns exit code directly in some modes */
#else
    int exitcode = WEXITSTATUS(rc);
#endif
    if (exitcode != 0) {
        fprintf(stderr, "[ir] helper exited with %d\n", exitcode);
        free(cmd); free(q_root); free(q_helper); free(q_index); free(q_extra);
        return 11;
    }

    free(cmd); free(q_root); free(q_helper); free(q_index); free(q_extra);
    return 0;
}

/* -------------------- stubs for native path (compile-ready) -------------------- */

IR_EnvTags *ir_detect_env(void) {
    IR_EnvTags *e = (IR_EnvTags *)calloc(1, sizeof(IR_EnvTags));
    return e;
}

void ir_free_env(IR_EnvTags *env) {
    if (!env) return;
    if (env->python_tag) free(env->python_tag);
    if (env->platform) free(env->platform);
    if (env->compatible_tags) {
        for (size_t i = 0; i < env->tags_len; ++i) free(env->compatible_tags[i]);
        free(env->compatible_tags);
    }
    free(env);
}

bool ir_normalize_name(const char *in, char **out) {
    if (!in || !out) return false;
    size_t n = strlen(in);
    char *buf = (char *)malloc(n * 2 + 1);
    if (!buf) return false;
    size_t j = 0; int dash = 0;
    for (size_t i = 0; i < n; ++i) {
        char c = in[i];
        if (c == '.' || c == '_' || c == '-') {
            dash = 1;
        } else {
            if (dash && j) buf[j++] = '-';
            dash = 0;
            if (c >= 'A' && c <= 'Z') c = (char)(c - 'A' + 'a');
            buf[j++] = c;
        }
    }
    buf[j] = 0;
    *out = buf;
    return true;
}

bool ir_parse_requirement(const char *req, IR_Requirement *out) {
    /* Stub: just fill name; real impl should follow PEP 440/508. */
    if (!req || !out) return false;
    memset(out, 0, sizeof(*out));
    char *norm = NULL;
    if (!ir_normalize_name(req, &norm)) return false;
    out->name = norm;
    return true;
}

bool ir_markers_match(const char *markers, const IR_EnvTags *env) {
    (void)markers; (void)env;
    return true; /* stub */
}

int ir_fetch_project_index(const char *base_simple, const char *project_norm,
                           char ***hrefs, size_t *hrefs_len) {
    (void)base_simple; (void)project_norm; (void)hrefs; (void)hrefs_len;
    return -2; /* ENOTSUP */
}

int ir_fetch_and_hash(const char *url, char **sha256_hex, char **tmp_path) {
    (void)url; (void)sha256_hex; (void)tmp_path;
    return -2;
}

bool ir_parse_filename_tags(const char *filename, IR_Artifact *a) {
    (void)filename; (void)a; return false;
}

bool ir_version_satisfies(const char *version, const char *specifier) {
    (void)version; (void)specifier; return true;
}

int ir_select_best_artifact(IR_Artifact *candidates, size_t n,
                            const IR_EnvTags *env, IR_Artifact **chosen) {
    (void)candidates; (void)n; (void)env; (void)chosen; return -2;
}

int ir_extract_metadata(const char *wheel_or_sdist_path,
                        IR_Requirement **requires_out, size_t *len_out) {
    (void)wheel_or_sdist_path; (void)requires_out; (void)len_out; return -2;
}

int ir_resolve_graph(IR_Requirement *roots, size_t roots_len,
                     const IR_EnvTags *env, IR_DepNode ***graph_out, size_t *graph_len) {
    (void)roots; (void)roots_len; (void)env; (void)graph_out; (void)graph_len; return -2;
}

int ir_write_lock_json(const char *path, IR_DepNode **graph, size_t n) {
    (void)path; (void)graph; (void)n; return -2;
}

int ir_write_pylock_toml(const char *path, IR_DepNode **graph, size_t n) {
    (void)path; (void)graph; (void)n; return -2;
}

int ir_emit_resolver_py(const char *path, IR_DepNode **graph, size_t n) {
    (void)path; (void)graph; (void)n; return -2;
}

void ir_free_graph(IR_DepNode **graph, size_t n) {
    (void)graph; (void)n;
}

/* -------------------- optional standalone -------------------- */
int ir_standalone_main(int argc, char **argv) {
    if (argc < 6) {
        fprintf(stderr,
            "Usage:\n"
            "  %s <root> <helper.py> <index> <extra-or-'-'> <req>...\n", argv[0]);
        return 1;
    }
    const char *root   = argv[1];
    const char *helper = argv[2];
    const char *index  = argv[3];
    const char *extra  = (strcmp(argv[4], "-") == 0) ? NULL : argv[4];
    const char **reqs  = (const char **)&argv[5];
    size_t n = (size_t)(argc - 5);
    return ir_resolve_with_helper(root, reqs, n, index, extra, "python3", helper);
}

#ifdef IR_STANDALONE
int main(int argc, char **argv) { return ir_standalone_main(argc, argv); }
#endif
