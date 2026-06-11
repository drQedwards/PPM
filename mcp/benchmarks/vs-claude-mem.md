# PMLL Memory MCP vs claude-mem — Head-to-Head Comparison

> **Keywords targeted**: `claude mem` (4,400 vol, $24.82 CPC), `claude-mem` (3,600 vol, $43.57 CPC)  
> **Last updated**: 2026-06-11  
> **PMLL version**: v2.0.3 | **claude-mem version**: latest

Looking for a `claude-mem` alternative? This page compares the two most popular session-memory tools for Claude Code and other MCP-compatible AI coding assistants.

---

## Quick Verdict

| Capability | PMLL (`pmll-memory-mcp`) | claude-mem |
|------------|--------------------------|------------|
| **Install** | `npx pmll-memory-mcp` | `npx claude-mem` |
| **License** | MIT | MIT |
| **Tools** | 15 | ~5 |
| **Short-term KV cache** | ✓ (`peek` pattern, 0ms) | ✗ |
| **Q-promise deduplication** | ✓ | ✗ |
| **Long-term memory graph** | ✓ (Context+ adapted) | ✗ |
| **Decay scoring** | ✓ (e^(-λt)) | ✗ |
| **Cross-session persistence** | ✓ | ✓ |
| **Auto-compress via LLM** | ✗ | ✓ (Haiku) |
| **Multi-tool support** | ✓ (Claude Code, Cursor, Windsurf, any MCP) | ✓ |
| **External API required** | ✗ | ✓ (Anthropic key for compression) |
| **Cloud sync** | Planned ($12/mo) | Available |
| **Context+ integration** | ✓ (recommended in Context+ README) | ✗ |
| **Benchmark (R@5)** | 91.3% (internal suite) | Not published |

---

## Architecture Difference

### claude-mem

claude-mem takes a compression-first approach: at the end of each session it uses Claude Haiku to summarise the conversation into a compact memory blob, which is injected at the start of the next session. Simple and effective for general chat.

**Strengths**: Automatic, opinionated, minimal config.  
**Weaknesses**: Requires an Anthropic API key and incurs per-session LLM costs. No structured retrieval — injects the full compressed blob regardless of relevance. No deduplication.

### PMLL (`pmll-memory-mcp`)

PMLL uses a two-layer architecture:

1. **Short-term KV silo** (`init` / `peek` / `set` / `flush`) — O(1) cache that eliminates redundant tool calls within a session. The `peek` pattern checks the silo before any expensive operation.
2. **Long-term memory graph** (`upsert_memory_node` / `search_memory_graph` / `prune_stale_links`) — persistent semantic graph adapted from [Context+](https://github.com/drQedwards/contextplus) with cosine-similarity search, typed edges, and exponential decay scoring.

The Q-promise bridge (`resolve` tool) prevents duplicate in-flight work when multiple tools fire concurrently — a problem claude-mem has no mechanism for.

---

## Use Case Fit

| If you need… | Use |
|--------------|-----|
| Minimal setup, general chat memory | claude-mem |
| Coding-specific session memory with 0ms cache hits | **PMLL** |
| Memory that works without an Anthropic API key | **PMLL** |
| Cross-tool memory (Cursor + Claude Code + Windsurf) | **PMLL** |
| Semantic graph you can query and traverse | **PMLL** |
| Auto-summarised natural language blobs | claude-mem |
| Context+ users wanting complementary memory | **PMLL** |

---

## Install Comparison

### PMLL

```bash
# One command — no API key, no config
npx pmll-memory-mcp
```

Add to Claude Code (`.mcp.json`):

```json
{
  "mcpServers": {
    "pmll-memory": {
      "command": "npx",
      "args": ["pmll-memory-mcp"]
    }
  }
}
```

### claude-mem

```bash
npx claude-mem
```

Requires `ANTHROPIC_API_KEY` in your environment for the Haiku compression step.

---

## Tool Surface

### PMLL — 15 tools

**Short-term (KV cache)**
- `init` — set up silo for a session
- `peek` — non-destructive context check (core dedup primitive)
- `set` — store a KV pair
- `resolve` — check/resolve a Q-promise continuation
- `flush` — clear session silo at task completion

**Long-term (memory graph)**
- `upsert_memory_node` — create/update a typed node with embeddings
- `create_memory_relation` — typed edges between nodes
- `search_memory_graph` — semantic search with graph traversal
- `prune_memory_links` — remove decayed edges and orphan nodes
- `add_interlinked_memory` — bulk-add with auto-similarity linking
- `retrieve_memory_traversal` — walk outward from a node

**Solution engine**
- `resolve_memory_context` — unified short+long term lookup
- `promote_memory_to_long_term` — elevate KV entry to graph
- `memory_status` — unified memory view

### claude-mem — ~5 tools

Read, write, list, delete, and summarise memory blobs. No graph structure, no semantic retrieval, no deduplication.

---

## Performance

| Operation | PMLL | claude-mem |
|-----------|------|------------|
| `peek` cache hit | **0ms** | N/A |
| Session `init` | ≤2ms | N/A |
| Memory write | ≤2ms | ~500ms (LLM call) |
| Memory read | ≤2ms | ~500ms (LLM call) |
| Cross-session inject | ≤36ms (TS) | ~500ms |

Speed benchmark: [speed-test-results.md](./speed-test-results.md)  
Accuracy benchmark: [accuracy-benchmark.md](./accuracy-benchmark.md)

---

## Pair With Context+

If you already use [Context+](https://github.com/drQedwards/contextplus) for codebase intelligence, PMLL is the natural companion:

- **Context+** handles structural awareness: AST trees, semantic code search, blast radius analysis
- **PMLL** handles session memory: what the agent decided, learned, and produced

Together the stack delivers 36ms (TypeScript) total context resolution with zero LLM calls per cache hit.

```json
{
  "mcpServers": {
    "contextplus": {
      "command": "npx",
      "args": ["-y", "contextplus"]
    },
    "pmll-memory": {
      "command": "npx",
      "args": ["pmll-memory-mcp"]
    }
  }
}
```

---

## FAQ

**Is PMLL a drop-in replacement for claude-mem?**  
For Claude Code users: yes for most workflows. The install command is the same pattern (`npx pmll-memory-mcp`) and it works with any MCP client. If you rely on Haiku's natural-language summarisation specifically, you may want to keep claude-mem alongside.

**Does PMLL work with Cursor and Windsurf?**  
Yes. PMLL is tool-agnostic — any MCP-compatible client works. claude-mem also supports multiple clients.

**Does PMLL require an API key?**  
No. Zero external dependencies. TF-IDF embeddings run locally with no GPU required.

**How does PMLL handle context that becomes outdated?**  
Edges decay via `e^(-λt)` over time. The `prune_memory_links` tool removes edges that fall below the decay threshold and orphaned low-access nodes. claude-mem has no decay mechanism — it injects the full blob every session.

---

## Resources

- [PMLL on npm](https://www.npmjs.com/package/pmll-memory-mcp)
- [PMLL source (drQedwards/PPM)](https://github.com/drQedwards/PPM)
- [Accuracy benchmark](./accuracy-benchmark.md)
- [Speed benchmark](./speed-test-results.md)
- [Context+ (complementary server)](https://github.com/drQedwards/contextplus)
