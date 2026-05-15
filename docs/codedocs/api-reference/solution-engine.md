---
title: "Solution Engine"
description: "Reference for the hybrid context-resolution functions exported by pmll_memory_mcp."
---

The solution engine module provides the high-level API for combining short-term and long-term memory.

## Import Path

```python
from pmll_memory_mcp import resolve_context, promote_to_long_term, get_memory_status
```

Source file: `mcp/pmll_memory_mcp/solution_engine.py`

## Functions

### `resolve_context`

```python
resolve_context(
    session_id: str,
    key: str,
    store: PMMemoryStore,
) -> dict[str, Any]
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `session_id` | `str` | — | Session whose graph should be searched on cache miss. |
| `key` | `str` | — | Lookup key or natural-language query. |
| `store` | `PMMemoryStore` | — | Short-term store checked first. |

Return shape:

```python
{"source": "short_term" | "long_term" | "miss", "value": str | None, "score": float}
```

### `promote_to_long_term`

```python
promote_to_long_term(
    session_id: str,
    key: str,
    value: str,
    node_type: NodeType = "concept",
    metadata: dict[str, str] | None = None,
) -> dict[str, Any]
```

Returns `{"promoted": True, "node_id": str}`.

### `get_memory_status`

```python
get_memory_status(
    session_id: str,
    store: PMMemoryStore,
) -> dict[str, Any]
```

Returns:

```python
{
    "short_term": {"slots": int, "silo_size": int},
    "long_term": {"nodes": int, "edges": int, "types": dict[str, int]},
    "promotion_threshold": 3,
}
```

## Example

```python
from pmll_memory_mcp import PMMemoryStore, promote_to_long_term, resolve_context, get_memory_status

sid = "api-ref-solution"
store = PMMemoryStore()
store.set("recent", "fresh summary")
promote_to_long_term(sid, "recent", "fresh summary", "note")

print(resolve_context(sid, "recent", store))
print(get_memory_status(sid, store))
```

## Notes

- `resolve_context()` always prefers the short-term store over graph search.
- `promotion_threshold` is informational in the current implementation.
- `promote_to_long_term()` is a thin wrapper around `upsert_node()`, so repeated promotions of the same `(label, type)` pair update the existing node instead of creating duplicates.
- `get_memory_status()` is safe to call for diagnostics because it does not mutate either memory layer.
- In the tested workflow under `mcp/tests/test_solution_engine.py`, the most important invariant is short-term priority: if both the cache and graph contain a value for the same logical key, the cache wins.
