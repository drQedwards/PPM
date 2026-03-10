# PMLL Memory MCP Server

> **Short-term KV context memory and Q-promise deduplication for Claude Sonnet/Opus agent tasks.**

[![MCP Registry](https://img.shields.io/badge/MCP-Registry%20Submission-blue)](https://github.com/modelcontextprotocol/servers)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](../LICENSE)
[![TypeScript](https://img.shields.io/badge/TypeScript-%3E%3D5.0-blue)](https://www.typescriptlang.org/)
[![Node.js](https://img.shields.io/badge/Node.js-%3E%3D18-green)](https://nodejs.org/)

---

## What it does

`pmll-memory-mcp` is a **Model Context Protocol (MCP) server** that gives Claude Sonnet/Opus agents a fast, session-isolated, short-term KV memory layer.  It is designed to be the **3rd initializer** alongside Playwright and other MCP tools — loaded once at the start of every agent task.

The server exposes five tools (`init`, `peek`, `set`, `resolve`, `flush`) that agents use to:

- **Cache** the results of expensive MCP tool calls (Playwright navigations, API fetches, …).
- **Deduplicate** redundant initializations by checking the cache before every tool invocation.
- **Chain async continuations** via a Q-promise registry so parallel agent subtasks don't repeat the same work.

---

## Why it's a premium 3rd initializer

Modern Claude agent tasks routinely call Playwright, file-system tools, and other MCP servers.  Without a shared memory layer, every subtask re-initializes the same context from scratch.  `pmll-memory-mcp` eliminates this overhead:

```
Agent task start
  ├── 1st init: Playwright MCP
  ├── 2nd init: Unstoppable Domains MCP  (see unstoppable-domains/)
  └── 3rd init: pmll-memory-mcp   ← this server
        └── all subsequent tool calls go through peek() first
```

---

## The `peek()` pattern

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

---

## Tools reference

| Tool      | Input                                              | Output                                                      | Description                                       |
|-----------|----------------------------------------------------|-------------------------------------------------------------|---------------------------------------------------|
| `init`    | `session_id: str`, `silo_size: int = 256`          | `{status, session_id, silo_size}`                           | Set up PMLL silo + Q-promise chain for session    |
| `peek`    | `session_id: str`, `key: str`                      | `{hit, value?, index?}` or `{hit, status, promise_id}`      | Non-destructive cache + promise check             |
| `set`     | `session_id: str`, `key: str`, `value: str`        | `{status: "stored", index}`                                 | Store KV pair in the silo                         |
| `resolve` | `session_id: str`, `promise_id: str`               | `{status: "resolved"\|"pending", payload?}`                 | Check/resolve a Q-promise continuation            |
| `flush`   | `session_id: str`                                  | `{status: "flushed", cleared_count}`                        | Clear all silo slots at task completion           |

---

## Installation

### Via `npx` (recommended — no install needed)

```bash
npx pmll-memory-mcp
```

### Via npm

```bash
npm install -g pmll-memory-mcp
pmll-memory-mcp          # starts the stdio MCP server
```

### Via pip (Python ≥ 3.11)

```bash
pip install pmll-memory-mcp
```

To install a specific version, use one of the following commands:

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

Once installed, start the server with:

```bash
pmll-memory-mcp          # stdio transport (default)
# or
python -m pmll_memory_mcp.server
```

### Claude Desktop / MCP config (`claude_desktop_config.json`)

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

---

## Docker

The MCP server ships as a multi-stage Docker image modelled on the
[upstream `memory` server](https://github.com/modelcontextprotocol/servers/tree/main/src/memory)
Dockerfile.

### Build

```bash
# From the repository root
docker build -f mcp/Dockerfile -t pmll-memory-mcp .
```

### Run

```bash
docker run --rm -i pmll-memory-mcp:latest
```

### Run (persistent KV memory via volume)

```bash
docker run --rm -i \
  -v pmll_data:/app/data \
  -e MEMORY_FILE_PATH=/app/data/memory.jsonl \
  pmll-memory-mcp:latest
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

#### pip

```json
{
  "servers": {
    "pmll-memory-mcp": {
      "command": "pmll-memory-mcp"
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

### Differences from the upstream `memory` Dockerfile

| | Upstream `src/memory` | This `mcp/` |
|---|---|---|
| **Build source** | `COPY src/memory /app` + `COPY tsconfig.json` | `COPY mcp /app` only |
| **tsconfig.json** | Extends root via `../../tsconfig.json` | Self-contained standalone |
| **Build command** | `npm install` + `npm ci --omit-dev` in builder | `npm install` + `npm run build` |
| **Persistence volume** | ❌ | ✅ `VOLUME ["/app/data"]` |
| **Entry point** | `node dist/index.js` | `node dist/index.js` ✓ |

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  pmll-memory-mcp                    │
│                                                     │
│  index.ts   ──►  peekContext()   ──►  kv-store.ts   │
│                       │                             │
│                       └──────────►  q-promise-bridge│
└─────────────────────────────────────────────────────┘
         │                    │
         ▼                    ▼
   PMLL.c / PMLL.h      Q_promise_lib/
   (memory_silo_t)       (QMemNode chain)
```

The server is **pure TypeScript** — no C compilation is required at runtime.  The KV store (`kv-store.ts`) mirrors the semantics of `PMLL.c::init_silo()` and `update_silo()` in TypeScript, and the promise registry (`q-promise-bridge.ts`) mirrors the `QMemNode` chain from `Q_promise_lib/Q_promises.h`.  Both C foundations are documented inline throughout the source.

### C foundations

| TypeScript module         | Mirrors                              | Key C primitives                    |
|---------------------------|--------------------------------------|-------------------------------------|
| `kv-store.PMMemoryStore`  | `PMLL.h::memory_silo_t`              | `init_silo()`, `update_silo()`      |
| `q-promise-bridge`        | `Q_promises.h::QMemNode`             | `q_mem_create_chain()`, `q_then()`  |
| `peek.peekContext()`      | Recursive conflict check in PMLL     | `check_conflict()`, `pml_refine()`  |

---

## Registry submission

This server is structured for submission to the [Anthropic official MCP registry](https://github.com/modelcontextprotocol/servers).  See `mcp_manifest.json` for the registry manifest.

---

## Companion servers

| Server | Directory | Transport | Description |
|--------|-----------|-----------|-------------|
| **Unstoppable Domains** | [`unstoppable-domains/`](./unstoppable-domains/) | HTTP (remote) | Search, purchase, and manage Web3 domain names via natural conversation. |

Use both servers together for the best agent experience: Unstoppable Domains handles domain operations while `pmll-memory-mcp` caches API responses to eliminate redundant network calls.  See [`unstoppable-domains/claude_desktop_config.json`](./unstoppable-domains/claude_desktop_config.json) for a combined Claude Desktop config.
