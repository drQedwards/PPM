#ifndef IMPORTRESOLVER_H
#define IMPORTRESOLVER_H

#include <stddef.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ---------- Data Types ---------- */

typedef struct {
    char *name;        /* normalized (PEP 503) */
    char *specifier;   /* raw PEP 440 specifier, may be NULL */
    char *markers;     /* PEP 508 markers, may be NULL */
    char *extras;      /* comma-separated extras, may be NULL */
} IR_Requirement;

typedef struct {
    char *filename;    /* wheel or sdist filename */
    char *url;         /* source URL */
    char *sha256;      /* hex digest */
    char *version;     /* normalized (PEP 440) */
    char *build;       /* wheel build tag or NULL */
    char *py_tag;      /* cp311, py3, etc. */
    char *abi_tag;     /* cp311, abi3, none, ... */
    char *plat_tag;    /* manylinux*, macosx-*, win_amd64, ... */
    bool  is_wheel;    /* true if .whl */
} IR_Artifact;

typedef struct IR_DepNode IR_DepNode;
struct IR_DepNode {
    char *name;
    char *version;
    IR_Artifact *artifacts;
    size_t artifacts_len;
    IR_Requirement *requires;   /* parsed Requires-Dist */
    size_t requires_len;
    IR_DepNode **children;
    size_t children_len;
};

typedef struct {
    char  *python_tag;     /* e.g., cp311 */
    char **compatible_tags;/* array of "py-abi-plat" strings ordered by pref */
    size_t tags_len;
    char  *platform;       /* descriptive platform string */
} IR_EnvTags;

/* ---------- High-level helper path (implemented) ---------- */

/**
 * Resolve requirements by invoking a Python helper (importresolver.py).
 * Produces:
 *   <root>/.ppm/lock.json
 *   <root>/pylock.toml
 *   <root>/resolver.py
 *
 * Returns 0 on success, non-zero on failure.
 */
int ir_resolve_with_helper(const char *root,
                           const char **reqs, size_t n_reqs,
                           const char *index_url,
                           const char *extra_index_url,
                           const char *py_exec,
                           const char *helper_path);

/* Backwards-compatible alias */
static inline int ir_resolve(const char *root,
                             const char **reqs, size_t n_reqs,
                             const char *index_url,
                             const char *extra_index_url,
                             const char *py_exec,
                             const char *helper_path)
{
    return ir_resolve_with_helper(root, reqs, n_reqs,
                                  index_url, extra_index_url,
                                  py_exec, helper_path);
}

/* ---------- Lower-level native API (stubbed for now) ---------- */

IR_EnvTags *ir_detect_env(void);
void        ir_free_env(IR_EnvTags *env);

bool ir_normalize_name(const char *in, char **out);          /* PEP 503 */
bool ir_parse_requirement(const char *req, IR_Requirement *out); /* PEP 440/508 (stub) */
bool ir_markers_match(const char *markers, const IR_EnvTags *env);

int  ir_fetch_project_index(const char *base_simple, const char *project_norm,
                            char ***hrefs, size_t *hrefs_len);
int  ir_fetch_and_hash(const char *url, char **sha256_hex, char **tmp_path);

bool ir_parse_filename_tags(const char *filename, IR_Artifact *a); /* PEP 425 */
bool ir_version_satisfies(const char *version, const char *specifier);

int  ir_select_best_artifact(IR_Artifact *candidates, size_t n,
                             const IR_EnvTags *env, IR_Artifact **chosen);

int  ir_extract_metadata(const char *wheel_or_sdist_path,
                         IR_Requirement **requires_out, size_t *len_out);

int  ir_resolve_graph(IR_Requirement *roots, size_t roots_len,
                      const IR_EnvTags *env, IR_DepNode ***graph_out, size_t *graph_len);

int  ir_write_lock_json(const char *path, IR_DepNode **graph, size_t n);
int  ir_write_pylock_toml(const char *path, IR_DepNode **graph, size_t n);
int  ir_emit_resolver_py(const char *path, IR_DepNode **graph, size_t n);

void ir_free_graph(IR_DepNode **graph, size_t n);

/* Optional standalone tester (compile with -DIR_STANDALONE) */
int ir_standalone_main(int argc, char **argv);

#ifdef __cplusplus
}
#endif
#endif /* IMPORTRESOLVER_H */
