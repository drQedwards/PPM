---
title: "Server Tools"
description: "Reference for the MCP-facing tool wrappers in the TypeScript and Python server entry points."
---

The server layer exposes the package through MCP tool wrappers. There are two relevant source files:

- TypeScript server: `mcp/src/index.ts`
- Python server: `mcp/pmll_memory_mcp/server.py`

## Canonical MCP Surface

The TypeScript server is the canonical tool surface because it includes all 15 tools advertised by the package manifest and README.

```text
init
peek
set
resolve
flush
graphql
upsert_memory_node
create_relation
search_memory_graph
prune_stale_links
add_interlinked_context
retrieve_with_traversal
resolve_context
promote_to_long_term
memory_status
```

## Python Wrapper Surface

The Python server exposes direct functions with near-equivalent behavior:

```python
from pmll_memory_mcp.server import (
    init,
    peek,
    set,
    resolve,
    flush,
    upsert_memory_node,
    create_memory_relation,
    search_memory_graph,
    prune_memory_links,
    add_interlinked_memory,
    retrieve_memory_traversal,
    resolve_memory_context,
    promote_memory_to_long_term,
    memory_status,
)
```

## Representative Signatures

### Short-term tools

```python
init(session_id: str, silo_size: int = 256) -> dict[str, Any]
peek(session_id: str, key: str) -> dict[str, Any]
set(session_id: str, key: str, value: str) -> dict[str, Any]
resolve(session_id: str, promise_id: str) -> dict[str, Any]
flush(session_id: str) -> dict[str, Any]
```

### Long-term tools

```python
upsert_memory_node(
    session_id: str,
    type: str,
    label: str,
    content: str,
    metadata: dict[str, str] | None = None,
) -> dict[str, Any]

create_memory_relation(
    session_id: str,
    source_id: str,
    target_id: str,
    relation: str,
    weight: float = 1.0,
) -> dict[str, Any]
```

### Solution-engine tools

```python
resolve_memory_context(session_id: str, key: str) -> dict[str, Any]
promote_memory_to_long_term(
    session_id: str,
    key: str,
    value: str,
    node_type: str = "concept",
) -> dict[str, Any]
memory_status(session_id: str) -> dict[str, Any]
```

## GraphQL Helper

The GraphQL tool is only implemented in TypeScript. Its underlying helper lives in `mcp/src/graphql.ts`:

```typescript
executeGraphQL(
  endpoint: string,
  operation: string,
  variables: Record<string, unknown> = {},
  headers: Record<string, string> = {},
): Promise<GraphQLResponse>
```

It also exports `GRAPHQL_QUERY`, `GRAPHQL_MUTATION`, and `GRAPHQL_DEFAULT_VARIABLES`.

## Example

```python
from pmll_memory_mcp.server import (
    init,
    set,
    upsert_memory_node,
    resolve_memory_context,
    memory_status,
)

sid = "server-tools-demo"
init(sid)
set(sid, "recent", "fresh output")
upsert_memory_node(sid, "note", "recent", "fresh output")
print(resolve_memory_context(sid, "recent"))
print(memory_status(sid))
```
