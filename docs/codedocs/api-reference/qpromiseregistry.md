---
title: "QPromiseRegistry"
description: "Reference for the in-flight promise registry and the peek_context helper."
---

`QPromiseRegistry` and `peek_context` are the package exports that implement in-flight deduplication.

## Import Paths

```python
from pmll_memory_mcp import QPromiseRegistry, peek_context
```

Source files:

- `mcp/pmll_memory_mcp/q_promise_bridge.py`
- `mcp/pmll_memory_mcp/peek.py`

## `QPromiseRegistry`

Constructor:

```python
QPromiseRegistry() -> None
```

### `register`

```python
register(promise_id: str) -> None
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `promise_id` | `str` | — | Unique identifier for an in-flight operation. |

### `resolve`

```python
resolve(promise_id: str, payload: str) -> bool
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `promise_id` | `str` | — | Promise to resolve. |
| `payload` | `str` | — | Final resolved value. |

Returns `True` when the promise existed.

### `peek_promise`

```python
peek_promise(promise_id: str) -> tuple[bool, str \| None, str \| None]
```

Returns `(found, status, payload)`.

### `__len__`

```python
__len__() -> int
```

### `__contains__`

```python
__contains__(promise_id: object) -> bool
```

## `peek_context`

```python
peek_context(
    key: str,
    session_id: str,
    store: PMMemoryStore,
    promise_registry: QPromiseRegistry,
) -> dict[str, Any]
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `key` | `str` | — | Context key to inspect. |
| `session_id` | `str` | — | Session identifier used by the caller. |
| `store` | `PMMemoryStore` | — | Session-local KV store. |
| `promise_registry` | `QPromiseRegistry` | — | Shared registry of in-flight work. |

Return shapes:

- `{"hit": True, "value": str, "index": int}`
- `{"hit": True, "status": "pending", "promise_id": str}`
- `{"hit": False}`

The implementation order matters: `peek_context()` checks the store before the registry. If you have already committed a value with `store.set()`, the function returns the cached payload even when an older promise record still exists.

## Example

```python
from pmll_memory_mcp import PMMemoryStore, QPromiseRegistry, peek_context

store = PMMemoryStore()
registry = QPromiseRegistry()
registry.register("session-1:fetch")

print(peek_context("session-1:fetch", "session-1", store, registry))
registry.resolve("session-1:fetch", "done")
store.set("session-1:fetch", "done")
print(peek_context("session-1:fetch", "session-1", store, registry))
```

## Notes

- The registry does not remove resolved promises automatically.
- Promise IDs should be namespaced by the caller, usually with the session ID embedded into the key.
