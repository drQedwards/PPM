---
name: ppm
description: Python Package Manager with persistent memory MCP tools for Context+, supermodeltools, and agent workflows. Use when working with PPM, pmll-memory-mcp via PPM, Context+ pipelines, context stitching, or packaging/agent memory tooling under drQedwards/ppm.
---

# PPM

Python Package Manager oriented around **persistent memory MCP tools** for agentic workflows — Context+ pipelines, supermodeltools/cli analysis, and structured memory ingestion/retrieval.

PPM is the packaging and tool surface that sits alongside PMLL-style spatial memory. Memory payloads stay **off-chain** by default. On-chain commitment anchoring (32-byte hashes only) is live on Stellar via **PMLL / `pmll-anchor`**, not via this package surface.

Typed off-chain **codework / episode** payload (byte-aligned with pmll): root [`skill.ts`](./skill.ts). `serializeCodework` / `hashCodework` → SHA-256 → `pmll-anchor` `store(id, commitment)`. Contract source and invoke docs live in [drQedwards/pmll](https://github.com/drQedwards/pmll); IDs below match `stellar.toml` (do not invent).

## Highlights

- PPM-based context stitching for agent memory and tool graphs.
- MCP tools for memory ingestion and retrieval (`init`, `peek`, `set`, `resolve`, `flush`, graph ops).
- **MCP compat:** `MCPServer` (mcp 2.x) with `FastMCP` fallback (mcp 1.x) in `mcp/pmll_memory_mcp/server.py` and `Ppm-lib/pmll_mcp/pmll_mcp_server.py`.
- Shared C core with PMLL (`PMLL.h` / `PMLL.c`, merged via PPM#70 / semantic-silo):
  - `memory_silo_t` — `tree` + `slots` / `embed_dim` (`PMLL_EMBED_DIM=32`) / `slot_count`
  - `peek` / `peek_semantic` dual-path (key|index, else cosine)
  - `silo_set`, `free_silo`, `silo_embed_text`, `silo_cosine_similarity`
  - `init_pml` sets `assignment[i] = -1` (undecided); `check_conflict` treats `-1` as undecided
  - SAT bridge: `sat_bridge_literal` / `sat_bridge_clause` / `sat_bridge_assignment_meanings` → associative memory strings
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


## Codework pickup (skill.ts → Soroban)

Off-chain only in this repo. Hash with [`skill.ts`](./skill.ts), then admin `store` on the verified `pmll-anchor` ID (contract lives in pmll):

```ts
import {
  exampleSemanticSiloCodework,
  hashCodework,
  toStoreArgs,
  PMLL_ANCHOR,
} from "./skill.ts";

const hash = await hashCodework(exampleSemanticSiloCodework({ skill: "ppm" }));
const { id, commitment } = toStoreArgs(hash);
// invoke pmll-anchor store -- see pmll SKILL.md / pmll-anchor/helper
```

Soroban ABI unchanged: `init` / `store(id, commitment)` / `get` / `bump` only. No invented fields.

## Related

- PMLL spatial memory skill: https://github.com/drQedwards/pmll/blob/main/SKILL.md
- Typed payload (mirrored): [`skill.ts`](./skill.ts)
- This repo: https://github.com/drQedwards/ppm
- Live on-chain commitments (32-byte hashes only) via `pmll-anchor`:
  - mainnet `CCF3B64AXLS4OLY5RN4H4K2CFZAYNZCJQY5MKCKCVAKMZNH7G7F7XUUF`
  - testnet `CDLQR24LLFWXTNGGJVJCRXAF3ZRDWFZRUFTDZ5SJOT2J33CS7DDYP7IU`
  - not part of the PPM package surface
- Network metadata: `stellar.toml`
