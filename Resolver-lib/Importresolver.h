#ifndef IMPORTRESOLVER_H
#define IMPORTRESOLVER_H

#include <stddef.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    char *name;           // normalized (pep503)
    char *specifier;      // raw requirement spec (pep440)
    char *markers;        // pep508 environment markers, may be NULL
    char *extras;         // comma-separated extras or NULL
} Requirement;

typedef struct {
    char *filename;       // wheel or sdist filename
    char *url;            // source URL
    char *sha256;         // hex digest
    char *version;        // normalized version (pep440)
    char *build;          // wheel build tag or NULL
    char *py_tag;         // cp310, py3, etc.
    char *abi_tag;        // abi3, cp310, none, ...
    char *plat_tag;       // manylinux2014_x86_64, macosx_..., win_amd64, ...
    bool  is_wheel;       // true if .whl
} Artifact;

typedef struct DepNode DepNode;
struct DepNode {
    char *name;
    char *version;
    Artifact *artifacts;  // chosen artifact(s) (usually 1)
    size_t artifacts_len;
    Requirement *requires; // parsed requires-dist from metadata
    size_t requires_len;
    DepNode **children;
    size_t children_len;
};

typedef struct {
    char *python_tag;     // computed from running interpreter (e.g., cp311)
    char **compatible_tags; // sorted list of pep425 tags "py-abi-plat"
    size_t tags_len;
    char *platform;       // linux/macos/windows details
} EnvTags;

// --- API ---
EnvTags *ir_detect_env(void);
void     ir_free_env(EnvTags*);

bool ir_normalize_name(const char *in, char **out); // pep503 normalization
bool ir_parse_requirement(const char *req, Requirement *out); // pep440+508 subset
bool ir_markers_match(const char *markers, const EnvTags *env);

int  ir_fetch_project_index(const char *base_simple, const char *project_norm,
                            char ***hrefs, size_t *hrefs_len); // list of files/urls
int  ir_fetch_and_hash(const char *url, char **sha256_hex, char **tmp_path);

bool ir_parse_filename_tags(const char *filename, Artifact *a); // pep425
bool ir_version_satisfies(const char *version, const char *specifier);

int  ir_select_best_artifact(Artifact *candidates, size_t n,
                             const EnvTags *env, Artifact **chosen);

int  ir_extract_metadata(const char *wheel_or_sdist_path,
                         Requirement **requires_out, size_t *len_out);

int  ir_resolve(Requirement *roots, size_t roots_len,
                const EnvTags *env, DepNode ***graph_out, size_t *graph_len);

int  ir_write_lock_json(const char *path, DepNode **graph, size_t n);
int  ir_write_pylock_toml(const char *path, DepNode **graph, size_t n);
int  ir_emit_resolver_py(const char *path, DepNode **graph, size_t n);

void ir_free_graph(DepNode **graph, size_t n);

#ifdef __cplusplus
}
#endif
#endif

#ifndef IMPORTRESOLVER_H
#define IMPORTRESOLVER_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stddef.h>

/**
 * Resolve Python requirements and emit:
 *   - <root>/.ppm/lock.json
 *   - <root>/pylock.toml
 *   - <root>/resolver.py
 *
 * Parameters:
 *   root: project root directory
 *   reqs: array of N requirement strings (e.g., "torch==2.7.0")
 *   n_reqs: size of reqs
 *   index_url: primary simple index (e.g., "https://pypi.org/simple")
 *   extra_index_url: optional extra index (e.g., "https://download.pytorch.org/whl/cu118") or NULL
 *   py_exec: python executable to invoke (e.g., "python3") or NULL to auto-detect "python3"
 *   helper_path: path to the Python helper script "importresolver.py"
 *
 * Returns 0 on success, non-zero on failure.
 */
int ir_resolve(const char *root,
               const char **reqs, size_t n_reqs,
               const char *index_url,
               const char *extra_index_url,
               const char *py_exec,
               const char *helper_path);

#ifdef __cplusplus
}
#endif

#endif /* IMPORTRESOLVER_H */
