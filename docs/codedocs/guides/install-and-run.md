---
title: "Install and Run"
description: "Install the package, start the MCP server, and verify the reusable Python API."
---

This guide covers the practical setup path that matches the source repository: install the published package, run the MCP server over stdio, and verify the underlying Python API with a short local script.

<Steps>
<Step>

### Install the package

Choose the runtime you need.

" "pip"]}>
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
<Tab value="pip">

```bash
pip install pmll-memory-mcp
```

</Tab>
</Tabs>

</Step>
<Step>

### Start the MCP server

For the Node implementation documented in `mcp/src/index.ts`, run:

```bash
npx pmll-memory-mcp
```

For the Python implementation documented in `mcp/pmll_memory_mcp/server.py`, run:

```bash
python -m pmll_memory_mcp.server
```

Both commands use stdio transport.

</Step>
<Step>

### Register it with an MCP client

Use the npm server as the canonical config because it matches the 15-tool TypeScript surface:

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

</Step>
<Step>

### Verify the reusable Python API

This script exercises the same logic without an MCP transport:

```python
from pmll_memory_mcp import (
    PMMemoryStore,
    QPromiseRegistry,
    peek_context,
    upsert_node,
    resolve_context,
)

session_id = "verify-install"
store = PMMemoryStore()
registry = QPromiseRegistry()

print(peek_context("search:docs", session_id, store, registry))
store.set("search:docs", "cached docs result")
upsert_node(session_id, "note", "docs", "cached docs result")
print(resolve_context(session_id, "docs", store))
```

Expected output:

```text
{'hit': False}
{'source': 'long_term', 'value': 'cached docs result', 'score': 1.0}
```

</Step>
</Steps>

## Why This Setup Order Matters

The package is designed so the reusable modules remain usable without the server, but the intended operational path is still "server first" for agents. That is why the TypeScript manifest exposes a `bin`, while the Python package also exports plain classes and functions from `__init__.py`.

<Callout type="info">If you only need the library surface, stop after the `pip install` step and import from <code>pmll_memory_mcp</code>. If you need MCP tools, use the Node server unless you specifically want the Python wrapper names.</Callout>
