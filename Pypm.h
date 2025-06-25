#ifndef PYPM_H
#define PYPM_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

// Version information
#define PYPM_VERSION "0.0.3-dev"
#define PYPM_API_VERSION 1

// Return codes
#define PYPM_SUCCESS 0
#define PYPM_ERROR_INVALID_ARGS 1
#define PYPM_ERROR_PLUGIN_LOAD 2
#define PYPM_ERROR_NETWORK 3
#define PYPM_ERROR_BUILD 4

// Configuration flags
#define PYPM_ENABLE_AUDIT true
#define PYPM_DEFAULT_CACHE_DIR "~/.cache/pypm"
#define PYPM_PLUGIN_DIR "~/.pypm/plugins"

// Plugin interface structure
typedef struct {
    const char* name;
    const char* version;
    int (*plugin_main)(int argc, char** argv);
    void* user_data;
} pypm_plugin_t;

// Core API function prototypes
int pypm_init(void);
void pypm_cleanup(void);
int pypm_plugin_load(const char* plugin_path, pypm_plugin_t** plugin);
int pypm_plugin_run(pypm_plugin_t* plugin, int argc, char** argv);
int pypm_doctor_check(void);
int pypm_sandbox_create(const char* dir);
int pypm_pypylock_bundle(const char* output_path);

// Audit-related function (for OSV/CVE integration)
int pypm_audit_scan(const char* package_list, char** report);

// Utility macros
#define PYPM_CHECK(expr) do { if (!(expr)) return PYPM_ERROR_##expr; } while(0)

// Plugin entry point (to be implemented by plugins)
#ifdef PYPM_PLUGIN_BUILD
    #define PYPM_PLUGIN_EXPORT __attribute__((visibility("default")))
#else
    #define PYPM_PLUGIN_EXPORT
#endif

PYPM_PLUGIN_EXPORT int pypm_plugin_main(int argc, char** argv);

#endif // PYPM_H
