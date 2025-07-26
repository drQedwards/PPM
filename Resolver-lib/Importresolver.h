#ifndef IMPORTRESOLVER_H
#define IMPORTRESOLVER_H

#include <stddef.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    char *name;        /* normalized (PEP 503) */
    char *specifier;   /* PEP 440 */
    char *markers;     /* PEP 508 */
    char *extras;      /* comma-separated extras */
} IR_Requirement;

typedef struct {
    char *filename;
    char *url;
    char *sha256;
    char *version;
    char *build;
    char *py_tag;
    char *abi_tag;
    char *plat_tag;
    bool  is_wheel;
} IR_Artifact;

typedef struct IR_DepNode IR_DepNode;
struct IR_DepNode {
    char *name;
    char *version;
    IR_Artifact *artifacts;
    size_t artifacts_len;
    IR_Requirement *requires;
    size_t requires_len;
    IR_DepNode **children;
    size_t children_len;
};

typedef struct {
    char  *python_tag;
    char **compatible_tags;
    size_t tags_len;
    char  *platform;
} IR_EnvTags;

/* ---------------- High-level helper path ---------------- */

int ir_resolve_with_helper(const char *root,
                           const char **reqs, size_t n_reqs,
                           const char *index_url,
                           const char *extra_index_url,
                           const char *py_exec,
                           const char *helper_path);

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

/* ---------------- CUDA hardened matrix ---------------- */

/**
 * Verify all artifact hashes with CUDA and emit a report.
 *
 * Inputs produced by the Python helper:
 *   <root>/.ppm/matrix_inputs.txt   ; TSV: "filename<TAB>sha256"
 *   <root>/.ppm/cache/<filename>    ; artifact bytes
 *   <root>/.ppm/matrix_plan.json    ; chosen platform (e.g., "cu126")
 *
 * Outputs:
 *   <root>/.ppm/matrix_report.json  ; results + mismatches
 *
 * Returns 0 on success. *out_mismatch_count receives number of hash mismatches.
 */
int ir_matrix_verify_cuda(const char *root,
                          const char *matrix_inputs_path,
                          const char *report_path,
                          int *out_mismatch_count);
/**
 * Verify Ed25519 signatures for artifacts, with GPU SHA-256 integrity checks.
 *
 * signatures_json_path: JSON file with fields:
 *   {
 *     "mode": "raw" | "ph",
 *     "items": [
 *       {"filename": "...", "sha256": "...", "pubkey": "<base64>", "sig": "<base64>"}
 *     ]
 *   }
 *
 * report_json_path: output JSON with per-file results.
 *
 * Returns 0 on success. Outputs invalid signature and hash mismatch counts.
 */
int ir_signature_verify_cuda(const char *root,
                             const char *signatures_json_path,
                             const char *report_json_path,
                             int *out_invalid_sig_count,
                             int *out_hash_mismatch_count);
/* ---------------- Native (stub) API ---------------- */

IR_EnvTags *ir_detect_env(void);
void        ir_free_env(IR_EnvTags *env);
bool ir_normalize_name(const char *in, char **out);
bool ir_parse_requirement(const char *req, IR_Requirement *out);
bool ir_markers_match(const char *markers, const IR_EnvTags *env);
int  ir_fetch_project_index(const char *base_simple, const char *project_norm,
                            char ***hrefs, size_t *hrefs_len);
int  ir_fetch_and_hash(const char *url, char **sha256_hex, char **tmp_path);
bool ir_parse_filename_tags(const char *filename, IR_Artifact *a);
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

int ir_standalone_main(int argc, char **argv);

#ifdef __cplusplus
}
#endif
#endif /* IMPORTRESOLVER_H */
