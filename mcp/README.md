# PMLL Memory MCP Server

> **Short-term KV context memory and Q-promise deduplication for Claude Sonnet/Opus agent tasks.**

[![MCP Registry](https://img.shields.io/badge/MCP-Registry%20Submission-blue)](https://github.com/modelcontextprotocol/servers)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](../LICENSE)
[![Python ≥ 3.11](https://img.shields.io/badge/python-%3E%3D3.11-blue)](https://www.python.org/)

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

```python
# Pseudocode — what the agent does automatically via MCP tool calls

# 1. Check cache before navigating
result = mcp.call("pmll-memory-mcp", "peek", {"session_id": sid, "key": "https://example.com"})
if result["hit"]:
    page_content = result["value"]          # ← served from PMLL silo, no browser needed
else:
    # 2. Cache miss — do the real work
    page_content = mcp.call("playwright", "navigate", {"url": "https://example.com"})
    # 3. Populate the cache for future agents / subtasks
    mcp.call("pmll-memory-mcp", "set", {
        "session_id": sid,
        "key": "https://example.com",
        "value": page_content,
    })
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

### Via `uvx` (recommended — no install needed)

```bash
uvx pmll-memory-mcp
```

### Via pip

```bash
pip install pmll-memory-mcp
pmll-memory-mcp          # starts the stdio MCP server
```

### Claude Desktop / MCP config (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "pmll-memory-mcp": {
      "command": "uvx",
      "args": ["pmll-memory-mcp"]
    }
  }
}
```

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  pmll-memory-mcp                    │
│                                                     │
│  server.py  ──►  peek_context()  ──►  kv_store.py  │
│                       │                             │
│                       └──────────►  q_promise_bridge│
└─────────────────────────────────────────────────────┘
         │                    │
         ▼                    ▼
   PMLL.c / PMLL.h      Q_promise_lib/
   (memory_silo_t)       (QMemNode chain)
```

The server is **pure Python** — no C compilation is required at runtime.  The KV store (`kv_store.py`) mirrors the semantics of `PMLL.c::init_silo()` and `update_silo()` in Python, and the promise registry (`q_promise_bridge.py`) mirrors the `QMemNode` chain from `Q_promise_lib/Q_promises.h`.  Both C foundations are documented inline throughout the source.

### C foundations

| Python module           | Mirrors                              | Key C primitives                    |
|-------------------------|--------------------------------------|-------------------------------------|
| `kv_store.PMMemoryStore`| `PMLL.h::memory_silo_t`              | `init_silo()`, `update_silo()`      |
| `q_promise_bridge`      | `Q_promises.h::QMemNode`             | `q_mem_create_chain()`, `q_then()`  |
| `peek.peek_context()`   | Recursive conflict check in PMLL     | `check_conflict()`, `pml_refine()`  |

---

## Registry submission

This server is structured for submission to the [Anthropic official MCP registry](https://github.com/modelcontextprotocol/servers).  See `mcp_manifest.json` for the registry manifest.

---

## Companion servers

| Server | Directory | Transport | Description |
|--------|-----------|-----------|-------------|
| **Unstoppable Domains** | [`unstoppable-domains/`](./unstoppable-domains/) | HTTP (remote) | Search, purchase, and manage Web3 domain names via natural conversation. |

Use both servers together for the best agent experience: Unstoppable Domains handles domain operations while `pmll-memory-mcp` caches API responses to eliminate redundant network calls.  See [`unstoppable-domains/claude_desktop_config.json`](./unstoppable-domains/claude_desktop_config.json) for a combined Claude Desktop config.
