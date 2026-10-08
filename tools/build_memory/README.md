# tools/build_memory: build results as PMLL memory

These scripts turn a batch build of this repo into memory nodes that an agent can
read back later.

```bash
python tools/build_memory/batch_build.py --out build_results.json        # compile everything, record it
python tools/build_memory/build_to_memory.py build_results.json \
       --load-sqlite ~/.local/share/pmll/memory_graph.sqlite3            # nodes + edges -> SQLite graph
python tools/build_memory/build_to_memory.py --stale ~/.local/share/pmll/memory_graph.sqlite3
```

- `batch_build.py` runs `tools/ci/batch_build_check.py`, which uses the same unit list and
  flags as the `batch-build` CI job. It adds the HEAD commit, a timestamp and the compiler
  versions. It records results and always exits 0. The CI job's `batch-build-results.json`
  artifact uses the same unit format, so you can also feed that file in.
- `build_to_memory.py` writes `memory_nodes.json` (nodes, edges and silo keys). With
  `--load-sqlite`, it also writes them through `mcp/pmll_memory_mcp.memory_graph`.
  With `--stale`, it lists files whose content changed since the last recorded build.

## Node model

Labels are the stable keys, because the graph upserts by `(type, label)`.

| type | label | content / metadata |
|---|---|---|
| file | `src:<sha256>` | One node per unique file content: status, warnings, first error, kind, whether it is required |
| file | `path:<repo>/<path>` | Pointer to the content last built (`metadata.sha256`) |
| concept | `module:<stem>` | Which kinds exist (c / c++ / pyx / cuda) and which units fail |
| note | `build:<run_id>` | HEAD, timestamp, toolchain, counts |

Edges: `module --contains--> path`, `path --references--> src`, `build --references--> src`,
and `src --depends_on--> src` for each `#include "..."` that resolves to a file inside the repo.

Silo keys: `build:<sha256>` maps to a compact status JSON. This is the key used by
`peek` / `set` and by the Q-promise loop: `Promise.from_peek(silo, key)` returns PENDING
on a miss; you compile, then `resolve_commit(status)` (see `Q_promise_lib/README.md`).

## Reading it back

- **Python API (persists):** `resolve_context(session, "src:<sha256>", store)` returns an
  exact label hit (`match: "exact"`, score 1.0). A never-stored key is a miss.
  `retrieve_with_traversal` walks module, path, source and header links.
- **MCP server:** load `memory_nodes.json` with `add_interlinked_context(items, auto_link=false)`.
  Then call `create_relation` for each edge, mapping labels to the node ids the server
  returns. Ids are generated on the server.

## What persists

| Store | Persists across process restarts? |
|---|---|
| Python `memory_graph` (SQLite at `PMLL_GRAPH_DB` or `~/.local/share/pmll/memory_graph.sqlite3`) | yes |
| Python / TS short-term KV (`set` / `peek`) | no (in process; `init` clears it) |
| TS `memory-graph.ts` (the npm `pmll-memory-mcp` server) | no (in-process `Map`) |
| C silo / Q-promises (`PMLL.c`, `qpromise.c`) | no (process memory) |

Staleness is detected by content hash. If a file's sha256 differs from its `path:` node,
the stored result describes older code.
