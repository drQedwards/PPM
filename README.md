# PPM — Python Package Manager

**pypm** packaging CLI with shared **PMLL** memory + Q-promise. Sibling: [drQedwards/pmll](https://github.com/drQedwards/pmll).

![CI](https://img.shields.io/badge/build-passing-brightgreen)
![License](https://img.shields.io/badge/license-MIT-blue)
![Version](https://img.shields.io/badge/pypm-0.0.3--dev-yellow)
[![npm](https://img.shields.io/npm/v/pmll-memory-mcp?label=pmll-memory-mcp)](https://www.npmjs.com/package/pmll-memory-mcp)
[![Sponsor](https://img.shields.io/badge/sponsor-DrQedwards-ea4aaa?logo=github-sponsors)](https://github.com/sponsors/DrQedwards)

Live Stellar `pmll-anchor` IDs: [docs/STELLAR.md](docs/STELLAR.md) · skills: [SKILL.md](SKILL.md) · promises: [Q_promise_lib/README.md](Q_promise_lib/README.md).

> **TL;DR**: PPM packages Python (C CLI). Shared **PMLL** owns **memory/state** (`memory_silo_t`, exact `peek` + semantic `peek_semantic`,
> SAT bridge, `init_pml`). Q-promise owns **temporal/control-flow** (`qpromise_*`, `libqpromise.so`)
> — it does **not** replace the silo. Optional Stellar commitments hash off-chain
> `CodeworkPayload`s into 32-byte digests via `pmll-anchor` (ABI: init/store/get/bump).
> Companion packaging CLI + MCP memory server live in-tree.

PMLL provides durable structured memory for agent workflows, alongside a PPM packaging CLI
(hermetic bundles, plugins, signing) and the [PMLL Memory MCP server](#-pmll-memory-mcp-server).
Long-term graph tools adapt [Context+](https://github.com/ForLoopCodes/contextplus).

---

## Table of Contents

1. [Layers (post-merge)](#layers-post-merge)
2. [Features](#-features)
3. [Building from Source](#-building-from-source)
4. [CLI Commands](#-cli-commands)
5. [GPU & Security Features](#-gpu--security-features)
6. [Plugin System](#-plugin-system)
7. [Configuration](#-configuration)
8. [PMLL Memory MCP Server](#-pmll-memory-mcp-server)
9. [Stellar commitments](#-stellar-commitments-pmll-anchor)
10. [Architecture](#-architecture)
11. [Release Notes](#-release-notes)
12. [Roadmap](#-roadmap)
13. [Contributing & Sponsors](#-contributing--sponsors)

---

---

## Layers (post-merge)

Two complementary layers — **not** substitutes for each other:

| Layer | Owns | Key surface |
|-------|------|-------------|
| **PMLL** | Durable memory / state | `memory_silo_t`, `peek` / `peek_semantic`, `silo_set`, SAT bridge, `init_pml` |
| **Q-promise** | Temporal / control-flow | `qpromise_*` API, `libqpromise.so`, deferred `qpromise_drain()` |

Q-promise does **not** replace the silo. A promise may *reference* a memory key (and optional SAT state id); results are committed back with `silo_set` / `qpromise_resolve_commit`.

### Intended loop

```
retrieve (peek / peek_semantic)
  → compute / request work
  → promise PENDING
  → resolve / reject (optionally resolve_commit → silo)
  → continuation (then / catch / finally via qpromise_drain)
  → memory update
  → retrieve again
```

**Thread safety:** the C Q-promise drain is **single-threaded**. Continuations run only during `qpromise_drain()` on the calling thread; callers must externally serialize access. Details: [`Q_promise_lib/README.md`](Q_promise_lib/README.md).

### C core (PMLL)

Headers: `PMLL.h` · implementation: `PMLL.c`

| Symbol | Role |
|--------|------|
| `memory_silo_t` | Associative/semantic silo: `tree`, `slots[]`, `embed_dim` (`PMLL_EMBED_DIM=32`), `slot_count` |
| `silo_slot_t` | `key`, `content`, `embedding`, `resolved` |
| `init_silo` / `free_silo` / `silo_set` | Allocate, free, write key/content + embedding |
| `peek` | Exact key, else index |
| `peek_semantic` | Cosine ≥ `min_sim` over embeddings (`silo_embed_text`, `silo_cosine_similarity`) |
| `init_pml` | Sets every `assignment[i] = -1` (**undecided**) |
| `check_conflict` | Treats `-1` as undecided (not sticky false from zero-fill) |
| `sat_bridge_*` | Map 3SAT tokens → associative string literals in the silo |

### Q-promise library

Build / test / API: **[`Q_promise_lib/README.md`](Q_promise_lib/README.md)** (authoritative). Public symbols are `qpromise_*`; shared object is `libqpromise.so`. The old prototype (`QMemNode` / `q_mem_*` / memory-chain walker) is removed; `Q_promises.h` is a compatibility include redirecting to `qpromise.h`.

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

### Q-promise shared library

```bash
cd Q_promise_lib
make clean && make test
make shared   # → libqpromise.so
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

> **Persistent memory logic loop with short-term KV context memory, Q-promise
> deduplication, and [Context+](https://github.com/ForLoopCodes/contextplus) long-term
> optional long-term semantic memory graph for agent tasks.**

[![npm](https://img.shields.io/npm/v/pmll-memory-mcp?label=pmll-memory-mcp)](https://www.npmjs.com/package/pmll-memory-mcp)
[![PyPI](https://img.shields.io/pypi/v/pmll-memory-mcp)](https://pypi.org/project/pmll-memory-mcp/)
[![MCP Registry](https://img.shields.io/badge/MCP-Registry%20Submission-blue)](https://github.com/modelcontextprotocol/servers)

`pmll-memory-mcp` is a **Model Context Protocol (MCP) server** with complementary
short-term KV and optional long-term graph layers. Server construction prefers
`MCPServer` (mcp 2.x) and falls back to `FastMCP` (mcp 1.x) — see
`mcp/pmll_memory_mcp/server.py`.

Ground tool names in code: TypeScript (`mcp/src/index.ts`) has 15 tools including
`graphql` and names like `create_relation`; Python (`mcp/pmll_memory_mcp/server.py`)
has 14 tools (no `graphql`) with several longer names such as `create_memory_relation`.
A ctypes demo in `Ppm-lib/pmll_mcp/` loads `libqpromise.so` via `qpromise_*`.

Memory layers:

- **Short-term KV cache** (5 tools) — session-isolated key-value memory with Q-promise deduplication, mirroring `PMLL.c::memory_silo_t`.
- **Long-term memory graph** (6 tools) — adapted from [Context+](https://github.com/ForLoopCodes/contextplus) by [@ForLoopCodes](https://github.com/ForLoopCodes), providing a persistent property graph with typed nodes, weighted edges, temporal decay scoring (e^(-λt)), and semantic search via TF-IDF embeddings.
- **Solution engine** (3 tools) — bridges both layers with unified context resolution (short-term → long-term → miss), auto-promotion of frequently accessed entries, and unified memory status views.

The server is designed to be the **3rd initializer** alongside Playwright and other MCP tools — loaded once at the start of every agent task. Agents call `init` once at task start, then use `peek` before any expensive MCP tool invocation to avoid redundant calls. Frequently accessed entries are promoted to the long-term memory graph for persistent semantic retrieval.

Tool counts differ by implementation (TS 15 incl. `graphql`; Python 14 — see note above). Historical docs below list the TypeScript tool surface.

### Why it's a premium 3rd initializer

Modern Claude agent tasks routinely call Playwright, file-system tools, and other MCP servers.  Without a shared memory layer, every subtask re-initializes the same context from scratch.  `pmll-memory-mcp` eliminates this overhead with two complementary memory layers:

```
Agent task start
  ├── 1st init: Playwright MCP
  ├── 2nd init: Unstoppable Domains MCP  (see unstoppable-domains/)
  └── 3rd init: pmll-memory-mcp   ← this server
        ├── Short-term: all tool calls go through peek() first
        └── Long-term: frequently accessed entries auto-promote to graph
```

### The `peek()` pattern

Before **every** expensive MCP tool invocation, agents call `peek` to check the cache:

```typescript
// Pseudocode — what the agent does automatically via MCP tool calls

// 1. Check cache before navigating
const result = mcp.call("pmll-memory-mcp", "peek", { session_id: sid, key: "https://example.com" });
if (result.hit) {
    const pageContent = result.value;          // ← served from PMLL silo, no browser needed
} else {
    // 2. Cache miss — do the real work
    const pageContent = mcp.call("playwright", "navigate", { url: "https://example.com" });
    // 3. Populate the cache for future agents / subtasks
    mcp.call("pmll-memory-mcp", "set", {
        session_id: sid,
        key: "https://example.com",
        value: pageContent,
    });
}
```

### Tools reference (15 tools)

#### Short-term KV memory (5 tools)

| Tool      | Input                                              | Output                                                      | Description                                       |
|-----------|----------------------------------------------------|-------------------------------------------------------------|---------------------------------------------------|
| `init`    | `session_id: str`, `silo_size: int = 256`          | `{status, session_id, silo_size}`                           | Set up PMLL silo + Q-promise state for session    |
| `peek`    | `session_id: str`, `key: str`                      | `{hit, value?, index?}` or `{hit, status, promise_id}`      | Non-destructive cache + promise check             |
| `set`     | `session_id: str`, `key: str`, `value: str`        | `{status: "stored", index}`                                 | Store KV pair in the silo                         |
| `resolve` | `session_id: str`, `promise_id: str`               | `{status: "resolved"\|"pending", payload?}`                 | Check/resolve a Q-promise continuation            |
| `flush`   | `session_id: str`                                  | `{status: "flushed", cleared_count}`                        | Clear all silo slots at task completion           |

#### GraphQL (1 tool)

| Tool      | Input                                                         | Output                  | Description                                              |
|-----------|---------------------------------------------------------------|-------------------------|----------------------------------------------------------|
| `graphql` | `query: str`, `variables?: object`, `operationName?: str`     | `{data}` or `{errors}`  | Execute GraphQL queries/mutations against the memory store |

#### Long-term memory graph (6 tools — adapted from [Context+](https://github.com/ForLoopCodes/contextplus))

These tools are adapted from [Context+](https://github.com/ForLoopCodes/contextplus) by [@ForLoopCodes](https://github.com/ForLoopCodes), providing persistent semantic memory with graph traversal, decay scoring, and cosine similarity search.

| Tool                      | Input                                                           | Output                                                | Description                                                                        |
|---------------------------|-----------------------------------------------------------------|-------------------------------------------------------|------------------------------------------------------------------------------------|
| `upsert_memory_node`      | `session_id`, `type`, `label`, `content`, `metadata?`           | `{node}`                                              | Create or update a memory node with auto-generated TF-IDF embeddings               |
| `create_relation`         | `session_id`, `source_id`, `target_id`, `relation`, `weight?`, `metadata?` | `{edge}`                                   | Create typed edges (relates_to, depends_on, implements, references, similar_to, contains) |
| `search_memory_graph`     | `session_id`, `query`, `max_depth?`, `top_k?`, `edge_filter?`  | `{direct, neighbors, totalNodes, totalEdges}`         | Semantic search with graph traversal — direct matches + neighbor walk              |
| `prune_stale_links`       | `session_id`, `threshold?`                                      | `{removed, remaining}`                                | Remove decayed edges (e^(-λt) below threshold) and orphan nodes with low access    |
| `add_interlinked_context` | `session_id`, `items[]`, `auto_link?`                           | `{nodes, edges}`                                      | Bulk-add nodes with auto-similarity linking (cosine ≥ 0.72 creates edges)          |
| `retrieve_with_traversal` | `session_id`, `start_node_id`, `max_depth?`, `edge_filter?`    | `[{node, depth, pathRelations, relevanceScore}]`      | Walk outward from a node — returns reachable neighbors scored by decay & depth     |

#### Solution engine (3 tools)

| Tool                   | Input                                             | Output                                                 | Description                                                           |
|------------------------|---------------------------------------------------|--------------------------------------------------------|-----------------------------------------------------------------------|
| `resolve_context`      | `session_id`, `key`                               | `{source, value, score}`                               | Unified context lookup: short-term KV → long-term graph → miss        |
| `promote_to_long_term` | `session_id`, `key`, `value`, `node_type?`, `metadata?` | `{promoted, nodeId}`                              | Promote a short-term KV entry to the long-term memory graph           |
| `memory_status`        | `session_id`                                      | `{shortTerm, longTerm, promotionThreshold}`            | Unified view of short-term KV and long-term graph memory status       |

### Installation

#### Via `npx` (recommended — no install needed)

```bash
npx pmll-memory-mcp
```

#### Via npm

```bash
npm install -g pmll-memory-mcp
pmll-memory-mcp          # starts the stdio MCP server
```

#### Via pip (Python)

```bash
pip install pmll-memory-mcp
pmll-memory-mcp          # starts the stdio MCP server
```

### Claude Desktop / MCP config (`claude_desktop_config.json`)

#### NPX

```json
{
  "tools": [
    {
      "name": "init",
      "description": "Set up PMLL silo and Q-promise state for a session. Call once at task start.",
      "inputSchema": {
        "type": "object",
        "properties": {
          "session_id": { "type": "string" },
          "silo_size": { "type": "integer", "default": 256 }
        },
        "required": ["session_id"]
      }
    },
    {
      "name": "peek",
      "description": "Non-destructive cache lookup + Q-promise check. Call before every expensive MCP tool invocation.",
      "inputSchema": {
        "type": "object",
        "properties": {
          "session_id": { "type": "string" },
          "key": { "type": "string" }
        },
        "required": ["session_id", "key"]
      }
    },
    {
      "name": "set",
      "description": "Store a key-value pair in the session silo. Call after a cache miss.",
      "inputSchema": {
        "type": "object",
        "properties": {
          "session_id": { "type": "string" },
          "key": { "type": "string" },
          "value": { "type": "string" }
        },
        "required": ["session_id", "key", "value"]
      }
    },
    {
      "name": "resolve",
      "description": "Check or resolve a Q-promise continuation by promise ID.",
      "inputSchema": {
        "type": "object",
        "properties": {
          "session_id": { "type": "string" },
          "promise_id": { "type": "string" }
        },
        "required": ["session_id", "promise_id"]
      }
    },
    {
      "name": "flush",
      "description": "Clear all silo slots for a session. Call at task completion.",
      "inputSchema": {
        "type": "object",
        "properties": {
          "session_id": { "type": "string" }
        },
        "required": ["session_id"]
      }
    },
    {
      "name": "graphql",
      "description": "Execute GraphQL queries or mutations against the memory store.",
      "inputSchema": {
        "type": "object",
        "properties": {
          "query": { "type": "string" },
          "variables": { "type": "object" },
          "operationName": { "type": "string" }
        },
        "required": ["query"]
      }
    },
    {
      "name": "upsert_memory_node",
      "description": "Create or update a memory node with auto-generated TF-IDF embeddings.",
      "inputSchema": {
        "type": "object",
        "properties": {
          "session_id": { "type": "string" },
          "type": { "type": "string" },
          "label": { "type": "string" },
          "content": { "type": "string" },
          "metadata": { "type": "object" }
        },
        "required": ["session_id", "type", "label", "content"]
      }
    },
    {
      "name": "create_relation",
      "description": "Create a typed, weighted edge between two memory nodes.",
      "inputSchema": {
        "type": "object",
        "properties": {
          "session_id": { "type": "string" },
          "source_id": { "type": "string" },
          "target_id": { "type": "string" },
          "relation": {
            "type": "string",
            "enum": ["relates_to", "depends_on", "implements", "references", "similar_to", "contains"]
          },
          "weight": { "type": "number" },
          "metadata": { "type": "object" }
        },
        "required": ["session_id", "source_id", "target_id", "relation"]
      }
    },
    {
      "name": "search_memory_graph",
      "description": "Semantic search with graph traversal — returns direct matches and neighbor walk.",
      "inputSchema": {
        "type": "object",
        "properties": {
          "session_id": { "type": "string" },
          "query": { "type": "string" },
          "max_depth": { "type": "integer" },
          "top_k": { "type": "integer" },
          "edge_filter": { "type": "string" }
        },
        "required": ["session_id", "query"]
      }
    },
    {
      "name": "prune_stale_links",
      "description": "Remove decayed edges (e^(-λt) below threshold) and orphan nodes with low access count.",
      "inputSchema": {
        "type": "object",
        "properties": {
          "session_id": { "type": "string" },
          "threshold": { "type": "number" }
        },
        "required": ["session_id"]
      }
    },
    {
      "name": "add_interlinked_context",
      "description": "Bulk-add nodes with auto-similarity linking (cosine >= 0.72 creates edges).",
      "inputSchema": {
        "type": "object",
        "properties": {
          "session_id": { "type": "string" },
          "items": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "type": { "type": "string" },
                "label": { "type": "string" },
                "content": { "type": "string" },
                "metadata": { "type": "object" }
              },
              "required": ["type", "label", "content"]
            }
          },
          "auto_link": { "type": "boolean" }
        },
        "required": ["session_id", "items"]
      }
    },
    {
      "name": "retrieve_with_traversal",
      "description": "Walk outward from a node, returning reachable neighbors scored by temporal decay and depth.",
      "inputSchema": {
        "type": "object",
        "properties": {
          "session_id": { "type": "string" },
          "start_node_id": { "type": "string" },
          "max_depth": { "type": "integer" },
          "edge_filter": { "type": "string" }
        },
        "required": ["session_id", "start_node_id"]
      }
    },
    {
      "name": "resolve_context",
      "description": "Unified context lookup: short-term KV -> long-term graph -> miss. Returns source and score.",
      "inputSchema": {
        "type": "object",
        "properties": {
          "session_id": { "type": "string" },
          "key": { "type": "string" }
        },
        "required": ["session_id", "key"]
      }
    },
    {
      "name": "promote_to_long_term",
      "description": "Promote a short-term KV entry to the long-term memory graph.",
      "inputSchema": {
        "type": "object",
        "properties": {
          "session_id": { "type": "string" },
          "key": { "type": "string" },
          "value": { "type": "string" },
          "node_type": { "type": "string" },
          "metadata": { "type": "object" }
        },
        "required": ["session_id", "key", "value"]
      }
    },
    {
      "name": "memory_status",
      "description": "Unified view of short-term KV and long-term graph memory status for a session.",
      "inputSchema": {
        "type": "object",
        "properties": {
          "session_id": { "type": "string" }
        },
        "required": ["session_id"]
      }
    }
  ]
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

### VS Code MCP configuration

Add to `.vscode/mcp.json` (or open **MCP: Open User Configuration** from the Command Palette):

#### NPX

```json
{
  "servers": {
    "pmll-memory-mcp": {
      "command": "npx",
      "args": ["-y", "pmll-memory-mcp"]
    }
  }
}
```

#### Docker

```json
{
  "servers": {
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

### Docker

```bash
# Build from the repository root
docker build -f mcp/Dockerfile -t pmll-memory-mcp .

# Run
docker run --rm -i pmll-memory-mcp:latest

# Run with persistent KV memory via volume
docker run --rm -i \
  -v pmll_data:/app/data \
  -e MEMORY_FILE_PATH=/app/data/memory.jsonl \
  pmll-memory-mcp:latest
```

### Companion servers & integrations

| Server / Integration | Directory / Source | Transport | Description |
|--------|-----------|-----------|-------------|
| **Unstoppable Domains** | [`unstoppable-domains/`](./unstoppable-domains/) | HTTP (remote) | Search, purchase, and manage Web3 domain names via natural conversation. |
| **Context+** | [github.com/ForLoopCodes/contextplus](https://github.com/ForLoopCodes/contextplus) | Integrated | Long-term semantic memory graph, adapted into `memory-graph.ts` and `solution-engine.ts`. By [@ForLoopCodes](https://github.com/ForLoopCodes). |

Full MCP server documentation: [`mcp/README.md`](mcp/README.md)

---

## ⚓ Stellar commitments (`pmll-anchor`)

Memory / codework payloads stay **off-chain**. Optional **32-byte SHA-256 commitments** are **live on Stellar mainnet** via Soroban `pmll-anchor` (shared with [`drQedwards/pmll`](https://github.com/drQedwards/pmll)).
ABI unchanged: `init` / `store` / `get` / `bump` only — do not invent fields or contract IDs.
This PPM tree may **not** include the full `pmll-anchor/` contract sources; typed payload is still mirrored as [`skill.ts`](./skill.ts).
Invoke docs / contract source: [pmll/SKILL.md](https://github.com/drQedwards/pmll/blob/main/SKILL.md). Local summary: [`SKILL.md`](./SKILL.md).

| Network | Contract ID | Explorer |
|---------|-------------|---------| 
| **mainnet** | `CCF3B64AXLS4OLY5RN4H4K2CFZAYNZCJQY5MKCKCVAKMZNH7G7F7XUUF` | [stellar.expert](https://stellar.expert/explorer/public/contract/CCF3B64AXLS4OLY5RN4H4K2CFZAYNZCJQY5MKCKCVAKMZNH7G7F7XUUF) |
| testnet | `CDLQR24LLFWXTNGGJVJCRXAF3ZRDWFZRUFTDZ5SJOT2J33CS7DDYP7IU` | [stellar.expert](https://stellar.expert/explorer/testnet/contract/CDLQR24LLFWXTNGGJVJCRXAF3ZRDWFZRUFTDZ5SJOT2J33CS7DDYP7IU) |

Admin: `GBFOFCD3XDANQWSGMHKJJ2V3YXS2QQD7RNC4LMDBVNBTUJOQZ3RLSB3E` · wasm hash `1b6ad9c574e0f5c9e39968f836a410c03adcf057afa93a63d2710bd30fdd53ba`

Skills summary: [`SKILL.md`](./SKILL.md) · full invoke docs: [pmll/SKILL.md](https://github.com/drQedwards/pmll/blob/main/SKILL.md)

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
│                  pmll-memory-mcp v1.0.1              │
│                                                     │
│  ┌──────────── Short-term (5 tools) ──────────┐    │
│  │ index.ts → peekContext() → kv-store.ts      │    │
│  │                  │                          │    │
│  │                  └──────► q-promise-bridge   │    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
│  ┌──────── Long-term — Context+ (6 tools) ────┐    │
│  │ memory-graph.ts → embeddings.ts             │    │
│  │ (nodes, edges, decay, cosine similarity)    │    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
│  ┌──────── Solution Engine (3 tools) ─────────┐    │
│  │ solution-engine.ts                          │    │
│  │ (resolve_context, promote, memory_status)   │    │
│  └─────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────┘
        │                    │
        ▼                    ▼
  PMLL.c / PMLL.h      Q_promise_lib/
  (memory_silo_t)       (qpromise_* / libqpromise.so)
```

### Key components

| File / Directory        | Purpose                                                          |
|-------------------------|------------------------------------------------------------------|
| `Ppm.c`                 | C-core CLI v0.0.3-dev — integrated single-file build (~500 LOC)  |
| `Pypm.c`                | PyPM 0.3.x front-door dispatcher; delegates to module sources    |
| `PMLL.c` / `PMLL.h`     | Associative/semantic silo, peek/peek_semantic, SAT bridge, init_pml=-1                |
| `SAT.c` / `SAT.h`       | Boolean SAT solver used for dependency resolution                |
| `Q_promise_lib/`        | Promise/continuation library (`qpromise_*`, `libqpromise.so`; single-threaded drain)  |
| `skill.ts` / `SKILL.md` | Off-chain CodeworkPayload + Stellar skills entry                 |
| `pmll-anchor/`          | Soroban commitment contract (source on pmll; may be absent here)                |
| `lattice/`              | On pmll only — playable Stellar skills graph / ARC-AGI-3 play test              |
| `mcp/`                  | TypeScript PMLL Memory MCP server (15 tools)                     |
| `mcp/src/memory-graph.ts` | Long-term memory graph adapted from [Context+](https://github.com/ForLoopCodes/contextplus) |
| `mcp/src/solution-engine.ts` | Solution engine bridging short-term KV + long-term graph    |
| `mcp/src/embeddings.ts`  | TF-IDF embeddings and cosine similarity for semantic search     |
| `CLI/`                  | Extended CLI interface                                           |
| `Panda-lib/` `Torch-lib/` `Numpy-lib/` | Library integration shims                       |
| `scripts/`              | Build helpers and automation scripts                             |

---

## 📝 Release Notes
### Post-merge (2026-08) — semantic silo + Q-promise

- PMLL C core: associative/semantic silo (`slots` + embeddings), `peek` + `peek_semantic`, SAT bridge, `init_pml` assignments start at `-1` (undecided).
- Q-promise evolved to `qpromise_*` + `libqpromise.so`; prototype `QMemNode` / `q_mem_*` API removed.
- Stellar skills / `skill.ts` aligned for off-chain `CodeworkPayload` hashing into existing `pmll-anchor` (ABI unchanged).
- MCP servers prefer `MCPServer` with `FastMCP` fallback; Q-promise MCP demos load `libqpromise.so`.


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

### pmll-memory-mcp 1.0.1

- **Version bump** — bumped from 1.0.0 to 1.0.1 to fix PyPI publishing (1.0.0 already existed on PyPI).
- **Updated project descriptions** — PyPI and npm package descriptions now include "in Claude Sonnet/Opus agent tasks" to match the mcp/README.md tagline.
- **README refresh** — PPM README.md MCP section updated with full tool reference, `peek()` pattern with TypeScript example, VS Code MCP configuration, and companion servers table from mcp/README.md.

### pmll-memory-mcp 1.0.0

- **Context+ integration** — 6 long-term memory graph tools adapted from
  [Context+](https://github.com/ForLoopCodes/contextplus) by
  [@ForLoopCodes](https://github.com/ForLoopCodes): `upsert_memory_node`,
  `create_relation`, `search_memory_graph`, `prune_stale_links`,
  `add_interlinked_context`, `retrieve_with_traversal`.
- **Solution engine** — 2 new tools + 1 status tool bridging short-term KV cache
  with long-term memory graph: `resolve_context`, `promote_to_long_term`,
  `memory_status`.
- **GraphQL tool** — `graphql` tool for flexible query/mutation access.
- 15 total tools (5 short-term KV + 1 GraphQL + 6 long-term graph + 3 solution engine).
- TF-IDF embeddings with cosine similarity search across the memory graph.
- Temporal decay scoring (e^(-λt)) on graph edges with automatic pruning.
- Auto-similarity linking (cosine ≥ 0.72) on bulk context additions.
- Unified context resolution path: short-term → long-term → miss.

### pmll-memory-mcp 0.2.0

- Initial MCP Registry submission.
- Five tools: `init`, `peek`, `set`, `resolve`, `flush`.
- TypeScript KV store mirroring `PMLL.c::memory_silo_t`.
- Q-promise registry (historical); current C API is `qpromise_*` / `libqpromise.so`.
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

*Built by **Dr. Q Josef Kurk Edwards** — making Python packaging fast, deterministic, and hackable, with a shared PMLL memory stack.*
