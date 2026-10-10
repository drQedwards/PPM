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
| concept | `module:<name>` | Which kinds exist (c / c++ / pyx / cuda / go / cgo) and which units fail. The name comes from the grouping function: file stem by default, or `--group dir` / `--group toplevel`, or any callable passed as `build(..., group=fn)` |
| note | `build:<run_id>` | HEAD, timestamp, toolchain, counts |

Edges: `module --contains--> path`, `path --references--> src`, `build --references--> src`,
and `src --depends_on--> src` for each `#include "..."` that resolves to a file inside the repo,
for each unit path listed in a unit's `depends_on_units`, and for each file in its `includes`.

Silo keys: `build:<sha256>` maps to a compact status JSON. This is the key used by
`peek` / `set` and by the Q-promise loop: `Promise.from_peek(silo, key)` returns PENDING
on a miss; you compile, then `resolve_commit(status)` (see `Q_promise_lib/README.md`).

## Reading it back

- **Python API (persists):** `resolve_context(session, "src:<sha256>", store)` returns an
  exact label hit (`match: "exact"`, score 1.0). A never-stored key is a miss.
  Structured keys (`path:`, `src:`, `module:`, `build:`) never fall back to semantic
  search unless you pass `min_score` or `exact_only=False`: on the go-ethereum graph,
  `path:go-ethereum/core/does-not-exist` scored 0.686 against `core/vm/program` and an
  all-zero `src:` scored 0.528 against `crypto/keccak`, both above the 0.5 cutoff.
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
the stored result describes older code. A `path:` node can also name a directory (a Go
package, say): its hash is `files_sha256` over the unit's `files` list, which is stored
on the node, or over the files directly in the directory when there is no list.
`stale_paths(..., hasher=fn)` takes a custom hash; `go_batch_build.go_package_hasher(root)`
re-lists packages so it also notices added files.

## Go modules

```bash
python tools/build_memory/go_batch_build.py /path/to/module --out go_build_results.json -j 4
python tools/build_memory/build_to_memory.py go_build_results.json \
       --root /path/to/module --group toplevel --load-sqlite graph.sqlite3
```

One unit per package (`go list -e -json ./...`): `go build -o /dev/null` (no binaries land
in the checkout; test-only packages count as built) and `go vet` (`--no-vet` skips it).
Intra-module imports, including test imports, become `depends_on_units`. A cgo package's
`#include "..."` closure is part of its hash and becomes header nodes. The target module
is not modified.

On go-ethereum v1.17.8 (204 packages, 8-core box, `-j 4`, Go build and vet caches
already warm) this took 62.8 s for build + vet; all 204 packages passed, and the graph
had 509 nodes and 2,290 edges. `stale_paths` then reported nothing, with either hasher.

## Loading at scale

`load_sqlite` writes everything in one transaction (`memory_graph.batch()`), and the
graph keeps label, (type, label), edge-key and adjacency indexes, so upserts no longer
scan the whole graph. `bench_load.py memory_nodes.json --scales 1 2 4 8` times it.
