---
title: "Memory Graph"
description: "Reference for the long-term graph functions exported by pmll_memory_mcp."
---

The memory graph module is the long-term retrieval engine behind semantic search and traversal.

## Import Path

```python
from pmll_memory_mcp import (
    upsert_node,
    create_relation,
    search_graph,
    prune_stale_links,
    add_interlinked_context,
    retrieve_with_traversal,
    get_graph_stats,
    clear_graph,
)
```

Source file: `mcp/pmll_memory_mcp/memory_graph.py`

## Functions

### `upsert_node`

```python
upsert_node(
    session_id: str,
    node_type: NodeType,
    label: str,
    content: str,
    metadata: dict[str, str] | None = None,
) -> MemoryNode
```

Creates or updates a typed node.

### `create_relation`

```python
create_relation(
    session_id: str,
    source_id: str,
    target_id: str,
    relation: RelationType,
    weight: float | None = None,
    metadata: dict[str, str] | None = None,
) -> MemoryEdge | None
```

Creates a typed edge or updates the weight of an existing duplicate.

### `search_graph`

```python
search_graph(
    session_id: str,
    query: str,
    max_depth: int = 1,
    top_k: int = 5,
    edge_filter: list[RelationType] | None = None,
) -> GraphSearchResult
```

Runs semantic search, then neighbor traversal.

### `prune_stale_links`

```python
prune_stale_links(
    session_id: str,
    threshold: float | None = None,
) -> dict[str, int]
```

Removes decayed edges and old orphan nodes.

### `add_interlinked_context`

```python
add_interlinked_context(
    session_id: str,
    items: list[dict[str, Any]],
    auto_link: bool = True,
) -> dict[str, Any]
```

Bulk-adds nodes and optional similarity edges.

### `retrieve_with_traversal`

```python
retrieve_with_traversal(
    session_id: str,
    start_node_id: str,
    max_depth: int = 2,
    edge_filter: list[RelationType] | None = None,
) -> list[TraversalResult]
```

Walks outward from a starting node.

### `get_graph_stats`

```python
get_graph_stats(session_id: str) -> dict[str, Any]
```

Returns node, edge, type, and relation counts.

### `clear_graph`

```python
clear_graph(session_id: str) -> int
```

Clears the graph for the session and returns the removed object count.

## Example

```python
from pmll_memory_mcp import (
    upsert_node,
    create_relation,
    search_graph,
    get_graph_stats,
)

sid = "api-ref-graph"
service = upsert_node(sid, "concept", "service", "Processes requests")
queue = upsert_node(sid, "concept", "queue", "Buffers jobs")
create_relation(sid, service.id, queue.id, "depends_on")

print(search_graph(sid, "job processing").direct[0].node.label)
print(get_graph_stats(sid))
```
