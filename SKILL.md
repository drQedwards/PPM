---
title: PMLL
description: Persistent spatial and hyperdimensional memory for AI agents on Stellar
---

# PMLL

Gives AI agents persistent spatial and hyperdimensional memory on Stellar so they can retain long-term context, form symbiotic memory layers, and maintain durable state across sessions.

PMLL demonstrates patterns for durable agent memory using the PPM project and integrates with Context+ pipelines and supermodeltools/cli for analysis and visualization.

## Highlights

- Persistent, addressable spatial and hyperdimensional memory mapped to Stellar accounts.
- PPM-based context stitching and MCP tools for memory ingestion and retrieval.
- Integration examples with forloopcodes/contextplus for hierarchical indexing and supermodeltools/cli for graphing and analysis.

## Quick start

1. Install PPM and PMLL helper tools:

```bash
pip install ppm
# Clone or install PMLL helpers (if needed)
```

2. Run a Context+ instance (or use an existing MCP):

```bash
# Start contextplus (example)
contextplus serve --db ./data
```

3. Ingest memory into PMLL via PPM's MCP tools or the provided ingestion scripts. See the `docs/` and `examples/` directories in the PPM repo for concrete commands.

## Usage examples

- Stitch short-term conversational context into long-lived memory using PPM's MCP ingestion APIs.
- Build symbiotic memory layers by combining per-agent spatial indexes with hyperdimensional vectors for semantic recall.
- Visualize memory graphs and call graphs with supermodeltools/cli to optimize retrieval and reduce token usage.

## Links

- PPM (package & MCP tools): https://github.com/drQedwards/PPM
- Context+: https://github.com/forloopcodes/contextplus
- supermodeltools/cli: https://github.com/supermodeltools/cli
- npm package: https://www.npmjs.com/package/pmll-memory-mcp

## License

MIT
