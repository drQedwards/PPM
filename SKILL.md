---
name: ppm
description: Python Package Manager with persistent memory MCP tools for Context+, supermodeltools, and agent workflows. Use when working with PPM, pmll-memory-mcp via PPM, Context+ pipelines, context stitching, or packaging/agent memory tooling under drQedwards/ppm.
---

# PPM

Python Package Manager oriented around **persistent memory MCP tools** for agentic workflows — Context+ pipelines, supermodeltools/cli analysis, and structured memory ingestion/retrieval.

PPM is the packaging and tool surface that sits alongside PMLL-style spatial memory. Memory payloads stay **off-chain** by default. On-chain commitment anchoring (32-byte hashes only) is live on Stellar via **PMLL / `pmll-anchor`**, not via this package surface.

## Highlights

- PPM-based context stitching for agent memory and tool graphs.
- MCP tools for memory ingestion and retrieval (`init`, `peek`, `set`, `resolve`, `flush`, graph ops).
- Works with forloopcodes/contextplus hierarchical indexing and supermodeltools/cli for graphing and analysis.
- Complements [drQedwards/pmll](https://github.com/drQedwards/pmll) spatial memory; does not claim Stellar storage of full memory payloads.

## Quick start

1. Install the memory MCP package (shared with the PMLL memory stack):

```bash
pip install pmll-memory-mcp
# or via npm: npx pmll-memory-mcp
# or: npm install -g pmll-memory-mcp
```

2. Register it with your MCP client (Claude Desktop example — `claude_desktop_config.json`):

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

(If installed via pip you can use `"command": "pmll-memory-mcp"` instead.)

3. Restart the client / start a fresh session. Call `init` once at the start of a task, then `peek` before expensive operations.

## Related

- PMLL spatial memory skill: https://github.com/drQedwards/pmll/blob/main/SKILL.md
- This repo: https://github.com/drQedwards/ppm
- Live on-chain commitments (32-byte hashes only) via `pmll-anchor`:
  - mainnet `CCF3B64AXLS4OLY5RN4H4K2CFZAYNZCJQY5MKCKCVAKMZNH7G7F7XUUF`
  - testnet `CDLQR24LLFWXTNGGJVJCRXAF3ZRDWFZRUFTDZ5SJOT2J33CS7DDYP7IU`
  - not part of the PPM package surface
