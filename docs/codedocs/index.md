---
title: "Getting Started"
description: "Start using the stable memory-layer package inside the PPM repository: pmll-memory-mcp."
---

`pmll-memory-mcp` is the reusable memory subsystem inside `/drqedwards/ppm`, combining a session-scoped KV cache, Q-promise deduplication, and a semantic memory graph for MCP agents.

## The Problem

- Agent workflows repeat the same expensive tool calls because there is no shared short-term memory between steps.
- Pure key-value caches are fast, but they cannot answer fuzzy or semantic lookups once a session ends.
- Long-term memory systems often depend on external embedding APIs, which makes local and air-gapped setups harder to run.
- Tool wrappers and memory logic usually get coupled together, which makes it difficult to test the core algorithms without running a full server.

## The Solution

Inside this repository, the stable package is `mcp/pmll_memory_mcp` for Python, with a matching TypeScript implementation in `mcp/src`. The design splits memory into short-term and long-term layers: `PMMemoryStore` handles deterministic session-local cache slots, `QPromiseRegistry` tracks in-flight work, and the memory graph adds semantic retrieval and traversal on top.

```python
from pmll_memory_mcp import (
    PMMemoryStore,
    QPromiseRegistry,
    peek_context,
    promote_to_long_term,
    resolve_context,
)

store = PMMemoryStore()
promises = QPromiseRegistry()
session_id = "demo-session"

print(peek_context("docs:index", session_id, store, promises))
store.set("docs:index", "cached home page payload")
print(resolve_context(session_id, "docs:index", store))
print(promote_to_long_term(session_id, "docs:index", "cached home page payload"))
```

## Installation

" "bun"]}>
<Tab value="npm">

```bash
npm install pmll-memory-mcp
```

</Tab>
<Tab value="pnpm">

```bash
pnpm add pmll-memory-mcp
```

</Tab>
<Tab value="yarn">

```bash
yarn add pmll-memory-mcp
```

</Tab>
<Tab value="bun">

```bash
bun add pmll-memory-mcp
```

</Tab>
</Tabs>

Python package:

```bash
pip install pmll-memory-mcp
```

Supported runtimes from the source manifests are Python `>=3.11` in `mcp/pyproject.toml` and Node.js `>=18` for the TypeScript server path in `mcp/package.json`.

## Quick Start

The minimum working example below uses the Python package surface exported from `mcp/pmll_memory_mcp/__init__.py`.

```python
from pmll_memory_mcp import (
    PMMemoryStore,
    QPromiseRegistry,
    peek_context,
    upsert_node,
    resolve_context,
)

session_id = "quickstart"
store = PMMemoryStore()
promises = QPromiseRegistry()

print(peek_context("auth-flow", session_id, store, promises))

store.set("auth-flow", "cached login sequence")
print(peek_context("auth-flow", session_id, store, promises))

upsert_node(session_id, "concept", "authentication", "cached login sequence")
print(resolve_context(session_id, "authentication", store))
```

Expected output:

```text
{'hit': False}
{'hit': True, 'value': 'cached login sequence', 'index': 0}
{'source': 'long_term', 'value': 'cached login sequence', 'score': 1.0}
```

## Key Features

- Session-isolated KV storage via `PMMemoryStore` in `mcp/pmll_memory_mcp/kv_store.py`
- In-flight deduplication via `QPromiseRegistry` and `peek_context`
- Dependency-free TF-IDF embeddings in `mcp/pmll_memory_mcp/embeddings.py`
- Long-term graph search, traversal, and edge decay in `mcp/pmll_memory_mcp/memory_graph.py`
- A solution engine that resolves from short-term first, then semantic long-term memory
- Two server implementations: TypeScript in `mcp/src/index.ts` and Python in `mcp/pmll_memory_mcp/server.py`

<Callout type="info">The PPM repository also contains C, CUDA, and older experimental MCP code. These docs focus on the package-quality memory server under <code>mcp/</code>, because that is the part with coherent manifests, tests, and reusable exports.</Callout>

<Cards>
  <Card title="Architecture" href="/docs/architecture">See how the Python package, TypeScript server, and memory layers fit together.</Card>
  <Card title="Core Concepts" href="/docs/kv-silo">Understand the short-term cache, promise registry, graph, and solution engine.</Card>
  <Card title="API Reference" href="/docs/api-reference/pmmemorystore">Review classes, functions, tool wrappers, signatures, and source locations.</Card>
</Cards>
