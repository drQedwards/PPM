# PMLL Memory MCP Server v2.0.0

> **Persistent memory logic loop with short-term KV cache (peek pattern), Q-promise
> deduplication, and [Context+](https://github.com/ForLoopCodes/contextplus) long-term
> memory graph designed to improve context retention and retrieval for coding agents.**
>
> **v2.0.0** — Four-way benchmarked, agent_instructions workflow, combined Context+ + PMLL/peek.

[![npm](https://img.shields.io/npm/v/pmll-memory-mcp)](https://www.npmjs.com/package/pmll-memory-mcp)
[![PyPI](https://img.shields.io/pypi/v/pmll-memory-mcp)](https://pypi.org/project/pmll-memory-mcp/)
[![MCP Registry](https://img.shields.io/badge/MCP-Registry%20Submission-blue)](https://github.com/modelcontextprotocol/servers)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](../LICENSE)
[![TypeScript](https://img.shields.io/badge/TypeScript-%3E%3D5.0-blue)](https://www.typescriptlang.org/)
[![Node.js](https://img.shields.io/badge/Node.js-%3E%3D18-green)](https://nodejs.org/)

---

## What's New in v2.0.0

- **Four-way speed benchmarks** — baseline, Context+-only, PMLL/peek-only, and combined (Context+ + PMLL/peek) configurations benchmarked in both TypeScript and Python with 5-run averages
- **Combined speed tests** — new `combined-speed.test.ts` (14 tests) and `test_combined_speed.py` (14 tests) proving both layers work together
- **Context+ standalone speed tests** — isolated `contextplus-speed.test.ts` (27 tests) and `test_contextplus_speed.py` (27 tests) benchmarking pure graph operations
- **agent_instructions.md** — mandatory agent workflow documentation defining the `peek()` pattern, tool priority, and Context+ tool reference for all 15 tools
- **Expanded test suites** — 197 TypeScript tests (8 files), 104 Python tests (6 files)
- **npm + PyPI dual publishing** — automated CI/CD for both registries on release

---

## Benchmark Results (v2.0.0)

Four-way speed comparison across both languages. Full details in [`benchmarks/three-way-speed-comparison.md`](./benchmarks/three-way-speed-comparison.md) (updated from 3-way to 4-way in v2.0.0).

**Retrieval quality (how we will measure later):** see [`benchmarks/benchmark_retrieval.md`](./benchmarks/benchmark_retrieval.md) and the runnable stub [`benchmarks/run_retrieval_stub.py`](./benchmarks/run_retrieval_stub.py). That harness defines retrieval hit rate on labeled nodes (precision@k / recall@k / MRR) — not agent task success. Speed numbers below are latency-only.

### TypeScript — Average Test Execution (5 runs)

| Configuration | Avg Test Time | Tests | Per-test |
|---------------|--------------|-------|----------|
| **Baseline (full suite)** | 302ms | 197 | 1.53ms |
| **Context+ only (no peek)** | 63ms | 27 | 2.33ms |
| **PMLL/peek only** | 26ms | 32 | 0.81ms |
| ⭐ **Combined (Context+ + PMLL/peek)** | **36ms** | 14 | 2.57ms |

### Python — Total Duration Averages (5 runs)

| Configuration | Avg Duration | Tests | Per-test |
|---------------|-------------|-------|----------|
| **Baseline (full suite)** | 250ms | 104 | 2.40ms |
| **Context+ only (no peek)** | 142ms | 27 | 5.26ms |
| **PMLL/peek only** | 92ms | 32 | 2.88ms |
| ⭐ **Combined (Context+ + PMLL/peek)** | **78ms** | 14 | 5.57ms |

### Per-Operation Highlights

| Operation | TypeScript | Python | Layer |
|-----------|-----------|--------|-------|
| `peek` cache hit | **0ms** | **<1ms** | PMLL/KV |
| `set` + `peek` round-trip | **≤2ms** | **≤3ms** | PMLL/KV |
| `upsert_memory_node` (100 nodes) | **6–7ms** | **~8ms** | Context+ graph |
| `search_memory_graph` (100 nodes, depth-2) | **7–8ms** | **~10ms** | Context+ graph |
| ⭐ **Graph search + cache + 50 peeks** | **≤8ms total** | **≤10ms total** | **Combined** |

### Key Findings

1. **Combined is the fastest total in Python** at 78ms — beating PMLL/peek-only (92ms) and Context+-only (142ms)
2. **In TypeScript**, combined (36ms) finishes nearly as fast as PMLL/peek-only (26ms) despite doing far more work per test
3. **The cache elimination pattern works**: 1 graph search (2–8ms) + 50 peek hits (0ms each) = 8ms total vs 50 × 8ms = 400ms without caching
4. **Both languages benefit equally** from the combined approach

---

## Agent Instructions (`agent_instructions.md`)

Every agent using this server **must** follow the workflow defined in [`agent_instructions.md`](./agent_instructions.md). Key requirements:

### The `peek()` Pattern (Mandatory)

1. **`init`** once at task start to set up the session silo
2. **`peek`** before every expensive MCP tool call — if hit, use cached value
3. **`set`** after a cache miss to populate the silo
4. **`resolve`** to check Q-promise continuations
5. **`flush`** at task end to clear session slots

### Tool Priority (Mandatory)

Agents MUST use Context+ tools instead of native equivalents:

| Instead of… | MUST use… | Why |
|---|---|---|
| `grep`, `rg` | `semantic_code_search` | Finds by meaning, not string match |
| `find`, `ls` | `get_context_tree` | Structure with symbols + line ranges |
| `cat`, read file | `get_file_skeleton` first | Signatures without wasting context |
| manual symbol tracing | `get_blast_radius` | Traces all usages across codebase |

### Execution Rules

- Think less, execute sooner: smallest safe change, validate quickly
- Batch independent reads/searches in parallel
- If a command fails, diagnose once, pivot strategy, cap retries to 1–2
- Start every task with `get_context_tree` or `get_file_skeleton`
- Run `get_blast_radius` BEFORE modifying or deleting any symbol
- Use `search_memory_graph` at task start, `upsert_memory_node` after completing work

See the full [agent_instructions.md](./agent_instructions.md) for the complete 15-tool reference and anti-patterns.

---

`pmll-memory-mcp` is a **Model Context Protocol (MCP) server** that gives Claude Sonnet/Opus agents a persistent memory logic loop with two complementary memory layers:

- **Short-term KV cache** (5 tools) — session-isolated key-value memory with Q-promise deduplication, mirroring `PMLL.c::memory_silo_t`.
- **Long-term memory graph** (6 tools) — adapted from [Context+](https://github.com/ForLoopCodes/contextplus) by [@ForLoopCodes](https://github.com/ForLoopCodes), providing a property graph with typed nodes, weighted edges, temporal decay scoring (e^(-λt)), and semantic search via stable hashing embeddings. **Python** persists the graph in SQLite; the **TypeScript** graph remains in-memory for the process lifetime.
- **Solution engine** (3 tools) — bridges both layers with unified context resolution (short-term → long-term → miss), auto-promotion of frequently accessed entries, and unified memory status views.

The server is designed to be the **3rd initializer** alongside Playwright and other MCP tools — loaded once at the start of every agent task. Agents call `init` once at task start, then use `peek` before any expensive MCP tool invocation to avoid redundant calls. Frequently accessed entries are promoted to the long-term memory graph for semantic retrieval across sessions (SQLite-backed on the Python server; in-memory on TypeScript).

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
| `init`    | `session_id: str`, `silo_size: int = 256`          | `{status, session_id, silo_size, cleared: true}`            | Set up / reset PMLL silo + Q-promise chain (`cleared` always true; `silo_size` is normalized) |
| `peek`    | `session_id: str`, `key: str`                      | `{hit, value?, index?}` or `{hit, status, promise_id}`      | Non-destructive cache + promise check             |
| `set`     | `session_id: str`, `key: str`, `value: str`        | `{status: "stored", index}`                                 | Store KV pair in the silo                         |
| `resolve` | `session_id: str`, `promise_id: str`               | `{status: "resolved"\|"pending", payload?}`                 | Check/resolve a Q-promise continuation            |
| `flush`   | `session_id: str`                                  | `{status: "flushed", cleared_count}`                        | Clear all silo slots at task completion           |

### GraphQL (1 tool)

| Tool      | Input                                                         | Output                  | Description                                              |
|-----------|---------------------------------------------------------------|-------------------------|----------------------------------------------------------|
| `graphql` | `query: str`, `variables?: object`, `operationName?: str`     | `{data}` or `{errors}`  | Execute GraphQL queries/mutations against the memory store |

### Long-term memory graph (6 tools — adapted from [Context+](https://github.com/ForLoopCodes/contextplus))

These tools are adapted from [Context+](https://github.com/ForLoopCodes/contextplus) by [@ForLoopCodes](https://github.com/ForLoopCodes), providing semantic memory with graph traversal, decay scoring, and cosine similarity search. Persistence: **Python** uses SQLite; **TypeScript** keeps the graph in-memory.

| Tool                      | Input                                                           | Output                                                | Description                                                                        |
|---------------------------|-----------------------------------------------------------------|-------------------------------------------------------|------------------------------------------------------------------------------------|
| `upsert_memory_node`      | `session_id`, `type`, `label`, `content`, `metadata?`           | `{node}`                                              | Create or update a memory node with auto-generated stable hashing embeddings               |
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
│                pmll-memory-mcp v2.0.0               │
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

The long-term memory graph (`memory-graph.ts`) is adapted from [Context+](https://github.com/ForLoopCodes/contextplus) by [@ForLoopCodes](https://github.com/ForLoopCodes), providing an in-memory property graph with typed nodes, weighted edges, temporal decay scoring (e^(-λt)), and semantic search via stable hashing embeddings. The solution engine (`solution-engine.ts`) bridges both layers, enabling unified context resolution and auto-promotion of frequently accessed short-term entries to the long-term graph.

### C foundations & Context+ integration

| TypeScript module              | Mirrors / Adapted from                        | Key primitives                        |
|--------------------------------|-----------------------------------------------|---------------------------------------|
| `kv-store.PMMemoryStore`       | `PMLL.h::memory_silo_t`                       | `init_silo()`, `update_silo()`        |
| `q-promise-bridge`             | `Q_promises.h::QMemNode`                      | `q_mem_create_chain()`, `q_then()`    |
| `peek.peekContext()`           | Recursive conflict check in PMLL              | `check_conflict()`, `pml_refine()`    |
| `memory-graph.ts`              | [Context+](https://github.com/ForLoopCodes/contextplus) memory graph | Nodes, edges, decay, traversal |
| `embeddings.ts`                | [Context+](https://github.com/ForLoopCodes/contextplus) embeddings   | Stable hashing embeds (TF-IDF legacy), cosine similarity |
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
