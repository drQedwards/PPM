# PMLL Memory MCP Server

> **Persistent memory logic loop with short-term KV context memory, Q-promise
> deduplication, and [Context+](https://github.com/ForLoopCodes/contextplus) long-term
> semantic memory graph for 99% accuracy in Claude Sonnet/Opus agent tasks.**

[![MCP Registry](https://img.shields.io/badge/MCP-Registry%20Submission-blue)](https://github.com/modelcontextprotocol/servers)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](../LICENSE)
[![TypeScript](https://img.shields.io/badge/TypeScript-%3E%3D5.0-blue)](https://www.typescriptlang.org/)
[![Node.js](https://img.shields.io/badge/Node.js-%3E%3D18-green)](https://nodejs.org/)

---

## What it does

`pmll-memory-mcp` is a **Model Context Protocol (MCP) server** that gives Claude Sonnet/Opus agents a persistent memory logic loop with two complementary memory layers:

- **Short-term KV cache** (5 tools) — session-isolated key-value memory with Q-promise deduplication, mirroring `PMLL.c::memory_silo_t`.
- **Long-term memory graph** (6 tools) — adapted from [Context+](https://github.com/ForLoopCodes/contextplus) by [@ForLoopCodes](https://github.com/ForLoopCodes), providing a persistent property graph with typed nodes, weighted edges, temporal decay scoring (e^(-λt)), and semantic search via TF-IDF embeddings.
- **Solution engine** (3 tools) — bridges both layers with unified context resolution (short-term → long-term → miss), auto-promotion of frequently accessed entries, and unified memory status views.

The server is designed to be the **3rd initializer** alongside Playwright and other MCP tools — loaded once at the start of every agent task. Agents call `init` once at task start, then use `peek` before any expensive MCP tool invocation to avoid redundant calls. Frequently accessed entries are promoted to the long-term memory graph for persistent semantic retrieval.

The server exposes **15 tools** total across four categories.

---

## Why it's a premium 3rd initializer

Modern Claude agent tasks routinely call Playwright, file-system tools, and other MCP servers.  Without a shared memory layer, every subtask re-initializes the same context from scratch.  `pmll-memory-mcp` eliminates this overhead with two complementary memory layers:

```
Agent task start
  ├── 1st init: Playwright MCP
  ├── 2nd init: Unstoppable Domains MCP  (see unstoppable-domains/)
  └── 3rd init: pmll-memory-mcp   ← this server
        ├── Short-term: all tool calls go through peek() first
        └── Long-term: frequently accessed entries auto-promote to graph
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

## Tools reference (15 tools)

### Short-term KV memory (5 tools)

| Tool      | Input                                              | Output                                                      | Description                                       |
|-----------|----------------------------------------------------|-------------------------------------------------------------|---------------------------------------------------|
| `init`    | `session_id: str`, `silo_size: int = 256`          | `{status, session_id, silo_size}`                           | Set up PMLL silo + Q-promise chain for session    |
| `peek`    | `session_id: str`, `key: str`                      | `{hit, value?, index?}` or `{hit, status, promise_id}`      | Non-destructive cache + promise check             |
| `set`     | `session_id: str`, `key: str`, `value: str`        | `{status: "stored", index}`                                 | Store KV pair in the silo                         |
| `resolve` | `session_id: str`, `promise_id: str`               | `{status: "resolved"\|"pending", payload?}`                 | Check/resolve a Q-promise continuation            |
| `flush`   | `session_id: str`                                  | `{status: "flushed", cleared_count}`                        | Clear all silo slots at task completion           |

### GraphQL (1 tool)

| Tool      | Input                                                         | Output                  | Description                                              |
|-----------|---------------------------------------------------------------|-------------------------|----------------------------------------------------------|
| `graphql` | `query: str`, `variables?: object`, `operationName?: str`     | `{data}` or `{errors}`  | Execute GraphQL queries/mutations against the memory store |

### Long-term memory graph (6 tools — adapted from [Context+](https://github.com/ForLoopCodes/contextplus))

These tools are adapted from [Context+](https://github.com/ForLoopCodes/contextplus) by [@ForLoopCodes](https://github.com/ForLoopCodes), providing persistent semantic memory with graph traversal, decay scoring, and cosine similarity search.

| Tool                      | Input                                                           | Output                                                | Description                                                                        |
|---------------------------|-----------------------------------------------------------------|-------------------------------------------------------|------------------------------------------------------------------------------------|
| `upsert_memory_node`      | `session_id`, `type`, `label`, `content`, `metadata?`           | `{node}`                                              | Create or update a memory node with auto-generated TF-IDF embeddings               |
| `create_relation`         | `session_id`, `source_id`, `target_id`, `relation`, `weight?`, `metadata?` | `{edge}`                                   | Create typed edges (relates_to, depends_on, implements, references, similar_to, contains) |
| `search_memory_graph`     | `session_id`, `query`, `max_depth?`, `top_k?`, `edge_filter?`  | `{direct, neighbors, totalNodes, totalEdges}`         | Semantic search with graph traversal — direct matches + neighbor walk              |
| `prune_stale_links`       | `session_id`, `threshold?`                                      | `{removed, remaining}`                                | Remove decayed edges (e^(-λt) below threshold) and orphan nodes with low access    |
| `add_interlinked_context` | `session_id`, `items[]`, `auto_link?`                           | `{nodes, edges}`                                      | Bulk-add nodes with auto-similarity linking (cosine ≥ 0.72 creates edges)          |
| `retrieve_with_traversal` | `session_id`, `start_node_id`, `max_depth?`, `edge_filter?`    | `[{node, depth, pathRelations, relevanceScore}]`      | Walk outward from a node — returns reachable neighbors scored by decay & depth     |

### Solution engine (3 tools)

| Tool                   | Input                                             | Output                                                 | Description                                                           |
|------------------------|---------------------------------------------------|--------------------------------------------------------|-----------------------------------------------------------------------|
| `resolve_context`      | `session_id`, `key`                               | `{source, value, score}`                               | Unified context lookup: short-term KV → long-term graph → miss        |
| `promote_to_long_term` | `session_id`, `key`, `value`, `node_type?`, `metadata?` | `{promoted, nodeId}`                              | Promote a short-term KV entry to the long-term memory graph           |
| `memory_status`        | `session_id`                                      | `{shortTerm, longTerm, promotionThreshold}`            | Unified view of short-term KV and long-term graph memory status       |

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
│                pmll-memory-mcp v1.0.1               │
│                                                     │
│  ┌────────── Short-term (5 tools) ────────────┐    │
│  │ index.ts  ──► peekContext()  ──► kv-store.ts│    │
│  │                    │                        │    │
│  │                    └────────► q-promise-bridge│   │
│  └─────────────────────────────────────────────┘    │
│                                                     │
│  ┌──── Long-term — Context+ (6 tools) ────────┐    │
│  │ memory-graph.ts ──► embeddings.ts           │    │
│  │ (nodes, edges, decay scoring, similarity)   │    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
│  ┌──── Solution Engine (3 tools) ─────────────┐    │
│  │ solution-engine.ts                          │    │
│  │ (resolve_context, promote, memory_status)   │    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
│  ┌──── GraphQL (1 tool) ─────────────────────┐     │
│  │ graphql.ts                                 │     │
│  └────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────┘
         │                    │
         ▼                    ▼
   PMLL.c / PMLL.h      Q_promise_lib/
   (memory_silo_t)       (QMemNode chain)
```

The server is **pure TypeScript** — no C compilation is required at runtime.  The KV store (`kv-store.ts`) mirrors the semantics of `PMLL.c::init_silo()` and `update_silo()` in TypeScript, and the promise registry (`q-promise-bridge.ts`) mirrors the `QMemNode` chain from `Q_promise_lib/Q_promises.h`.

The long-term memory graph (`memory-graph.ts`) is adapted from [Context+](https://github.com/ForLoopCodes/contextplus) by [@ForLoopCodes](https://github.com/ForLoopCodes), providing an in-memory property graph with typed nodes, weighted edges, temporal decay scoring (e^(-λt)), and semantic search via TF-IDF embeddings. The solution engine (`solution-engine.ts`) bridges both layers, enabling unified context resolution and auto-promotion of frequently accessed short-term entries to the long-term graph.

### C foundations & Context+ integration

| TypeScript module              | Mirrors / Adapted from                        | Key primitives                        |
|--------------------------------|-----------------------------------------------|---------------------------------------|
| `kv-store.PMMemoryStore`       | `PMLL.h::memory_silo_t`                       | `init_silo()`, `update_silo()`        |
| `q-promise-bridge`             | `Q_promises.h::QMemNode`                      | `q_mem_create_chain()`, `q_then()`    |
| `peek.peekContext()`           | Recursive conflict check in PMLL              | `check_conflict()`, `pml_refine()`    |
| `memory-graph.ts`              | [Context+](https://github.com/ForLoopCodes/contextplus) memory graph | Nodes, edges, decay, traversal |
| `embeddings.ts`                | [Context+](https://github.com/ForLoopCodes/contextplus) embeddings   | TF-IDF, cosine similarity     |
| `solution-engine.ts`           | Bridges short-term KV + Context+ long-term    | `resolveContext()`, `promoteToLongTerm()` |

---

## Registry submission

This server is structured for submission to the [Anthropic official MCP registry](https://github.com/modelcontextprotocol/servers).  See `mcp_manifest.json` for the registry manifest.

---

## Companion servers & integrations

| Server / Integration | Directory / Source | Transport | Description |
|--------|-----------|-----------|-------------|
| **Unstoppable Domains** | [`unstoppable-domains/`](./unstoppable-domains/) | HTTP (remote) | Search, purchase, and manage Web3 domain names via natural conversation. |
| **Context+** | [github.com/ForLoopCodes/contextplus](https://github.com/ForLoopCodes/contextplus) | Integrated | Long-term semantic memory graph, adapted into `memory-graph.ts` and `solution-engine.ts`. By [@ForLoopCodes](https://github.com/ForLoopCodes). |

Use all integrations together for the best agent experience: Unstoppable Domains handles domain operations, Context+ provides long-term semantic memory, and `pmll-memory-mcp` caches API responses to eliminate redundant network calls.  See [`unstoppable-domains/claude_desktop_config.json`](./unstoppable-domains/claude_desktop_config.json) for a combined Claude Desktop config.
