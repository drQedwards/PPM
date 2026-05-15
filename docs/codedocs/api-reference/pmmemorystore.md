---
title: "PMMemoryStore"
description: "Reference for the short-term KV store class exported by pmll_memory_mcp."
---

`PMMemoryStore` is the short-term session cache exported from `pmll_memory_mcp` and implemented in `mcp/pmll_memory_mcp/kv_store.py`.

## Import Path

```python
from pmll_memory_mcp import PMMemoryStore
```

Source file: `mcp/pmll_memory_mcp/kv_store.py`

## Constructor

```python
PMMemoryStore(silo_size: int = 256) -> None
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `silo_size` | `int` | `256` | Informational silo capacity carried on the instance. |

## Public Methods

### `peek`

```python
peek(key: str) -> tuple[bool, str \| None, int \| None]
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `key` | `str` | — | Cache key to inspect. |

Returns a tuple `(hit, value, index)`.

Example:

```python
store = PMMemoryStore()
print(store.peek("user:1"))
```

### `set`

```python
set(key: str, value: str) -> int
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `key` | `str` | — | Cache key to store. |
| `value` | `str` | — | Resolved string payload. |

Returns the slot index used for the entry.

Example:

```python
store = PMMemoryStore()
slot = store.set("user:1", "{"name": "Ada"}")
print(slot)
```

### `flush`

```python
flush() -> int
```

Returns the number of slots cleared.

Example:

```python
store = PMMemoryStore()
store.set("a", "1")
store.set("b", "2")
print(store.flush())
```

### `__len__`

```python
__len__() -> int
```

Returns the number of stored slots.

### `__contains__`

```python
__contains__(key: object) -> bool
```

Returns `True` when the key exists in the store.

## Common Combined Pattern

```python
from pmll_memory_mcp import PMMemoryStore

store = PMMemoryStore()

if not store.peek("docs")[0]:
    store.set("docs", "cached docs payload")

print(len(store), "docs" in store)
```

## Notes

- Existing keys are updated in place and keep their original slot index.
- The constructor does not enforce a hard limit on writes.
- The server wrappers usually create instances indirectly through `get_store(session_id)` in the same source module, which is why application code should think in terms of session lifecycle rather than a single global cache.
- Because `peek()` only reports resolved values, it pairs naturally with `peek_context()` when you also need to account for in-flight work.
