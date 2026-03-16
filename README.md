# PPM — Python Package Manager

**pypm** – the "npm-style" package manager for Python  
*C-powered core · reproducible installs · plugin-friendly · workspace-aware*

![CI](https://img.shields.io/badge/build-passing-brightgreen)
![License](https://img.shields.io/badge/license-MIT-blue)
![Version](https://img.shields.io/badge/pypm-0.0.3--dev-yellow)
[![npm](https://img.shields.io/npm/v/pmll-memory-mcp?label=pmll-memory-mcp)](https://www.npmjs.com/package/pmll-memory-mcp)
[![Sponsor](https://img.shields.io/badge/sponsor-DrQedwards-ea4aaa?logo=github-sponsors)](https://github.com/sponsors/DrQedwards)

> **TL;DR**: `pypm` aims to be a **single command** that handles everything from creating a
> virtual-env to publishing wheels—fast, deterministic, and hackable.
> The current release is ~500 LOC of portable C that already boots a shell, diagnoses
> broken build chains, runs dynamically-loaded plugins, and produces hermetic bundles
> for air-gapped deploys.

PPM is a next-generation Python package manager featuring hermetic packaging,
GPU-accelerated verification, cryptographic signing, and a companion
[PMLL Memory MCP server](#-pmll-memory-mcp-server) for Claude agent tasks.

---

## Table of Contents

1. [Features](#-features)
2. [Building from Source](#-building-from-source)
3. [CLI Commands](#-cli-commands)
4. [GPU & Security Features](#-gpu--security-features)
5. [Plugin System](#-plugin-system)
6. [Configuration](#-configuration)
7. [PMLL Memory MCP Server](#-pmll-memory-mcp-server)
8. [Architecture](#-architecture)
9. [Release Notes](#-release-notes)
10. [Roadmap](#-roadmap)
11. [Contributing & Sponsors](#-contributing--sponsors)

---

## ✨ Features

| Command                    | What it does                                                                 |
|----------------------------|------------------------------------------------------------------------------|
| `pypm doctor`              | Checks Python headers, C compiler, OpenSSL, WASI toolchain, GPU, …          |
| `pypm sandbox [-d DIR]`    | Drops you into an ephemeral temp dir (or custom DIR) with a full shell       |
| `pypm plugin add NAME SRC` | Downloads a `.so` plugin (from URL or path) into `~/.pypm/plugins/`         |
| `pypm plugin run NAME …`   | Executes `pypm_plugin_main()` inside the named plugin                        |
| `pypm pypylock [-o FILE]`  | Bundles **every wheel + interpreter** into `dist/venv.tar.gz` (or FILE)     |
| `pypm version`             | Prints the current CLI version                                               |
| `ppm import PKG`           | Import and cache a package with GPU-accelerated hash verification            |
| `ppm add PKG --lock`       | Add packages and update the lockfile                                         |
| `ppm plan` / `ppm apply`   | Plan dependency changes, then apply them with an audit trail                 |
| `ppm snapshot` / `ppm rollback` | Snapshot the environment; roll back to any prior state               |
| `ppm sign` / `ppm verify`  | Sign artifacts (Ed25519) and verify cryptographic receipts                   |
| `ppm sbom`                 | Generate a Software Bill of Materials (SBOM)                                 |

*Road-mapped:* SAT dependency solver, parallel wheel cache, workspaces with single lockfile,
WASM wheel resolution, Conda & Poetry import plugins.

---

## 🔧 Building from Source

### System dependencies

- C11 compiler (`gcc`, `clang`, or MSVC)
- `libcurl` (plugin downloads)
- `libdl` (dynamic loading — standard on Linux / macOS)
- `tar` / `libarchive` (optional, for `pypylock` bundles)

### Build & first run

```bash
git clone https://github.com/drQedwards/PPM.git
cd PPM
cc -Wall -Wextra -ldl -lcurl -o pypm Ppm.c
./pypm doctor        # Diagnose your dev box
./pypm sandbox       # Spin up a throw-away REPL playground
```

### Optional: CUDA-accelerated build

```bash
nvcc -O3 CLI/CLI.cu -lcuda -o ppm-gpu
./ppm-gpu import transformers torch --verbose
```

---

## 🖥 CLI Commands

### Import packages

```bash
# Import a single package
ppm import transformers

# Import with a specific version
ppm import transformers==4.43.3

# Import multiple packages
ppm import transformers torch numpy

# Scan a Python file for imports and install them
ppm import --from-file my_script.py

# Verbose — watch what's happening
ppm import transformers --verbose
# 🔍 Resolving transformers...
# ⬇️  Downloading transformers-4.43.3-py3-none-any.whl
# 🔐 GPU integrity check: PASSED
# ✅ transformers==4.43.3 imported successfully
```

### Project initialization

```bash
ppm init
# Creates:
# .ppm/
# ├── ledger.jsonl      ← append-only operation log
# ├── state.json        ← current state
# ├── lock.json         ← dependency lockfile
# └── snapshots/        ← rollback points
```

### Dependency resolution & locking

```bash
ppm add transformers torch==2.4.0 --lock

ppm plan
# { "plan": "install", "packages": { "transformers": "4.43.3", ... } }

ppm apply --note "Added ML stack"
```

### Snapshot & rollback

```bash
ppm snapshot --name "before-upgrade"
ppm snapshots
ppm rollback before-upgrade
```

### Environment diagnostics

```bash
ppm doctor
# ✅ Python dev headers found
# ✅ C compiler available
# ✅ CUDA toolkit available
# 🏁 Diagnostics complete (0 issues found)
```

### Sandbox

```bash
ppm sandbox                 # ephemeral temp directory
ppm sandbox -d /tmp/mydir   # custom directory
```

### Hermetic packaging

```bash
ppm pypylock -o production-env.tar.gz
```

---

## 🔐 GPU & Security Features

### GPU-accelerated hash verification

```bash
ppm import torch --verbose
# 🚀 GPU hash verification: SHA-256 computed on device
# ✅ Integrity verified: e3b0c44298fc1c149afbf4c8996fb924...
```

### GPU backend selection

```bash
ppm ensure transformers --gpu auto    # auto-detect CUDA
ppm ensure transformers --gpu cu121  # force CUDA 12.1
ppm ensure transformers --gpu cpu    # CPU-only
```

### Ed25519 cryptographic signing

```bash
ppm keygen --out-priv ed25519.priv --out-pub ed25519.pub
ppm sign   --sk ed25519.priv --file torch-2.4.0-*.whl --gpu ./libbreath_gpu.so
ppm verify --receipt torch-2.4.0-*.whl.receipt.json   --file torch-2.4.0-*.whl
```

### Provenance & SBOM

```bash
ppm sbom        --out project-sbom.json
ppm provenance  --out provenance.json
ppm graph --dot | dot -Tpng -o deps.png
```

---

## 🔌 Plugin System

```bash
# Install a plugin
ppm plugin add auditwheel https://cdn.example.com/auditwheel.so

# Run it
ppm plugin run auditwheel repair --wheel torch-2.4.0-cp310-linux_x86_64.whl
```

### Writing a plugin (C)

```c
// hello.c
#include <stdio.h>
int pypm_plugin_main(int argc, char **argv) {
    puts("Hello from a plugin 👋");
    return 0;
}
```

```bash
cc -shared -fPIC -o hello.so hello.c
mv hello.so ~/.pypm/plugins/
pypm plugin run hello
```

---

## ⚙️ Configuration

### `pypm.toml`

```toml
[tool.ppm]
python = "^3.10"
default_gpu = "auto"

[tool.ppm.backends]
cpu.index   = "https://download.pytorch.org/whl/cpu"
cu121.index = "https://download.pytorch.org/whl/cu121"
cu122.index = "https://download.pytorch.org/whl/cu122"

torch_prefer        = "2.4.*"
transformers_prefer = "4.43.*"
```

### Environment variables

```bash
export PYP_WORKSPACE_ROOT=/path/to/project   # override workspace detection
export PYP_DEBUG=1                           # enable debug output
export CUDA_VISIBLE_DEVICES=0               # control GPU usage
```

---

## 🧠 PMLL Memory MCP Server

`pmll-memory-mcp` (v0.2.0) is a **Model Context Protocol (MCP) server** that gives
Claude Sonnet / Opus agents a fast, session-isolated, short-term KV memory layer.
It is designed as the **3rd initializer** alongside Playwright and other MCP tools.

### Installation

```bash
# Via npx (no install required)
npx pmll-memory-mcp

# Via npm
npm install -g pmll-memory-mcp
pmll-memory-mcp          # starts the stdio MCP server

# Via pip (Python ≥ 3.11)
pip install pmll-memory-mcp
```

To install a specific version via pip, use one of the following commands:

```bash
pip install pmll-memory-mcp==0.1.0
pip install pmll-memory-mcp==0.2.0
```

> **Notes:**
> - If you run both commands, the second will upgrade/replace 0.1.0 with 0.2.0 (you'll end up on 0.2.0).
> - To switch versions, explicitly install the version you want (or uninstall first):
>
> ```bash
> pip uninstall -y pmll-memory-mcp
> pip install pmll-memory-mcp==0.1.0
> ```

### Claude Desktop / MCP config

#### NPX

```json
{
  "mcpServers": {
    "pmll-memory-mcp": {
      "command": "npx",
      "args": ["pmll-memory-mcp"]
    }
  }
}
```

#### pip

```json
{
  "mcpServers": {
    "pmll-memory-mcp": {
      "command": "pmll-memory-mcp"
    }
  }
}
```

#### Docker

```json
{
  "mcpServers": {
    "pmll-memory-mcp": {
      "command": "docker",
      "args": [
        "run", "-i",
        "-v", "pmll_data:/app/data",
        "-e", "MEMORY_FILE_PATH=/app/data/memory.jsonl",
        "--rm", "pmll-memory-mcp"
      ]
    }
  }
}
```

### Tools reference

| Tool      | Inputs                                          | Output                                              | Description                                       |
|-----------|-------------------------------------------------|-----------------------------------------------------|---------------------------------------------------|
| `init`    | `session_id`, `silo_size = 256`                 | `{status, session_id, silo_size}`                   | Set up PMLL silo + Q-promise chain for session    |
| `peek`    | `session_id`, `key`                             | `{hit, value?, index?}` or `{hit, promise_id}`      | Non-destructive cache + promise check             |
| `set`     | `session_id`, `key`, `value`                    | `{status: "stored", index}`                         | Store KV pair in the silo                         |
| `resolve` | `session_id`, `promise_id`                      | `{status: "resolved"\|"pending", payload?}`         | Check / resolve a Q-promise continuation          |
| `flush`   | `session_id`                                    | `{status: "flushed", cleared_count}`                | Clear all silo slots at task completion           |

### The `peek()` pattern

```
Agent task start
  ├── 1st init: Playwright MCP
  ├── 2nd init: Unstoppable Domains MCP
  └── 3rd init: pmll-memory-mcp   ← this server
        └── all subsequent tool calls go through peek() first
```

### Docker build

```bash
# From the repository root
docker build -f mcp/Dockerfile -t pmll-memory-mcp .
docker run --rm -i pmll-memory-mcp:latest

# With persistent KV memory
docker run --rm -i \
  -v pmll_data:/app/data \
  -e MEMORY_FILE_PATH=/app/data/memory.jsonl \
  pmll-memory-mcp:latest
```

Full MCP server documentation: [`mcp/README.md`](mcp/README.md)

---

## 🏛 Architecture

```
┌───────────────┐
│ pypm (CLI)    │  ← C-based command parser
└───────┬───────┘
        │
        ▼
┌───────────────┐     ┌─────────────┐     ┌──────────────┐
│ Workspace     │◀───▶│ Resolver    │◀───▶│ Wheel Cache  │
│ (TOML / YAML) │     │ (SAT + PEP) │     │ (~/.cache)   │
└───────────────┘     └─────┬───────┘     └─────┬────────┘
                            │                   │
                            ▼                   ▼
                       ┌──────────┐       ┌────────────┐
                       │ Env Mgr  │       │ Plugin Host│
                       │ (.venv)  │       │ (dlopen)   │
                       └──────────┘       └────────────┘

┌─────────────────────────────────────────────────────┐
│                  pmll-memory-mcp                    │
│                                                     │
│  index.ts  ──►  peekContext()  ──►  kv-store.ts     │
│                      │                              │
│                      └─────────►  q-promise-bridge  │
└─────────────────────────────────────────────────────┘
        │                    │
        ▼                    ▼
  PMLL.c / PMLL.h      Q_promise_lib/
  (memory_silo_t)       (QMemNode chain)
```

### Key components

| File / Directory        | Purpose                                                          |
|-------------------------|------------------------------------------------------------------|
| `Ppm.c`                 | C-core CLI v0.0.3-dev — integrated single-file build (~500 LOC)  |
| `Pypm.c`                | PyPM 0.3.x front-door dispatcher; delegates to module sources    |
| `PMLL.c` / `PMLL.h`     | Persistent Memory Logic Loop — KV silo primitives                |
| `SAT.c` / `SAT.h`       | Boolean SAT solver used for dependency resolution                |
| `Q_promise_lib/`        | Q-promise / async continuation chain (mirrors JS Promises in C)  |
| `mcp/`                  | TypeScript PMLL Memory MCP server                                |
| `CLI/`                  | Extended CLI interface                                           |
| `Panda-lib/` `Torch-lib/` `Numpy-lib/` | Library integration shims                       |
| `scripts/`              | Build helpers and automation scripts                             |

---

## 📝 Release Notes

### pypm 0.0.3-dev (25 Jun 2025)

**New & Improved**

| Area                       | What's new                                                                         |
|----------------------------|------------------------------------------------------------------------------------|
| **Unified source**         | v0.0.1 + v0.0.2 merged into a single `pypm.c` file to simplify builds.            |
| **Version bump**           | CLI now reports `0.0.3-dev`.                                                       |
| **Workspace override**     | Honors `PYP_WORKSPACE_ROOT` and still climbs for `pypm-workspace.toml`.            |
| **Doctor v2.1**            | Counts issues and exits with that count; inline Python probe via here-doc.         |
| **Sandbox v2.1**           | `-d <DIR>` flag; default remains `mkdtemp`.                                        |
| **Plugin fetcher hardening** | Creates `~/.pypm/plugins` safely; `CURLOPT_FAILONERROR` for HTTP 4xx/5xx; preserves plugin exit code. |
| **Hermetic bundle flag**   | `pypylock -o <file>` works regardless of flag order; default `dist/venv.tar.gz`.   |
| **Error surfacing**        | `fatal()` now shows `errno` via `perror`; `dlopen`/`curl` errors bubble up.        |

**Fixes**
- CLI flags after sub-commands were occasionally skipped by `getopt` → `optind = 2` before parsing.
- Plugin loader returned success even when `dlsym` failed → now returns non-zero and closes handle.
- Workspace scan no longer overwrites `cwd` for later `getcwd()` calls.

**Breaking changes**
1. `pypm version` is now a sub-command (not `--version` flag).
2. `doctor` exit codes can now be >1 (numeric issue count).

**Migration (0.0.2 → 0.0.3-dev)**

| If you did …                         | Do this now                                          |
|--------------------------------------|------------------------------------------------------|
| `./pypm doctor && echo OK`           | Check `[[ $? -eq 0 ]]` or parse the numeric count.  |
| Used `pypm_v002.c` / `pypm_v001.c`   | Switch to `pypm.c`, `make clean && make`.            |
| Hard-coded `dist/venv.tar.gz` path   | Pass `-o` flag for custom output paths.              |

**Known issues**
- Windows build needs: `LoadLibraryW`, `_mktemp_s`, `bsdtar.exe` fallback (#22).
- `pypylock` relies on shell `tar`; `libarchive` port planned for 0.0.4.
- WASI/Rust/OpenSSL checks are informational stubs only.

---

### pmll-memory-mcp 0.2.0

- Initial MCP Registry submission.
- Five tools: `init`, `peek`, `set`, `resolve`, `flush`.
- TypeScript KV store mirroring `PMLL.c::memory_silo_t`.
- Q-promise registry mirroring `Q_promise_lib::QMemNode`.
- Docker multi-stage image with persistent volume support.
- Companion Unstoppable Domains MCP server included in `mcp/unstoppable-domains/`.

---

### pypm 0.0.2 (25 Jun 2025)

Workspace autodetect, Doctor v2, Sandbox upgrade, Plugin add/run, `pypylock -o`.
**Breaking**: `--version` flag removed; `doctor` exits non-zero on issues.

### pypm 0.0.1 (23 Jun 2025)

Initial proof-of-concept — single-file CLI with `doctor`, `sandbox`, `plugin`, and `pypylock`.

---

## 🗺 Roadmap

| Version | Planned features                                                           |
|---------|----------------------------------------------------------------------------|
| 0.0.4   | Lockfile parser + wheel copier for real hermetic bundles                   |
| 0.0.5   | `libsolv`-backed dependency resolver                                        |
| 0.1.0   | Cross-platform shims (Windows / macOS)                                     |
| 0.1.1   | WASI toolchain detection & wheel preference                                |
| future  | SAT dependency solver, parallel wheel cache, workspaces, WASM resolution   |

---

## 🤝 Contributing & Sponsors

Pull requests are welcome!  Open issues and PRs at  
**<https://github.com/drQedwards/PPM/issues>**

If you find PPM or `pmll-memory-mcp` useful, please consider supporting development:

[![GitHub Sponsors](https://img.shields.io/badge/Sponsor-DrQedwards-ea4aaa?logo=github-sponsors&style=for-the-badge)](https://github.com/sponsors/DrQedwards)
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-drqedwards-FFDD00?logo=buy-me-a-coffee&style=for-the-badge)](https://buymeacoffee.com/drqedwards)
[![CoinGecko Portfolio](https://img.shields.io/badge/CoinGecko-Portfolio-8DC63F?logo=coingecko&style=for-the-badge)](https://www.coingecko.com/en/portfolios/public/jkdrq)

---

*Built by **Dr. Q Josef Kurk Edwards** — making Python packaging fast, deterministic, and hackable.*
