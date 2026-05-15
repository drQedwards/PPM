---
title: "KV Silo"
description: "Learn how short-term memory works through PMMemoryStore and the session-scoped silo model."
---

The KV silo is the fast path in this package. `PMMemoryStore` in `mcp/pmll_memory_mcp/kv_store.py` stores resolved values by key and assigns each new key a stable slot index, mirroring the `memory_silo_t` idea referenced throughout the code comments.

## What It Is

`PMMemoryStore` is a per-session cache with three core operations:

- `peek(key)` checks whether a value is already resolved
- `set(key, value)` stores or updates a slot
- `flush()` clears the whole session

The point is not sophisticated cache eviction. The point is deterministic, cheap memory for one agent task.

## How It Relates To Other Concepts

- `peek_context()` builds on top of the store and adds the Q-promise pending check.
- `resolve_context()` uses the store as layer one before searching the semantic graph.
- The server wrappers call `get_store(session_id)` so every MCP session gets its own silo.

## How It Works Internally

In `mcp/pmll_memory_mcp/kv_store.py`, the internal `_KVSlot` dataclass stores `index`, `key`, `value`, and `resolved`. `PMMemoryStore.set()` checks whether the key already exists. If it does, the existing slot is updated in place and the original index is preserved. If it does not, the new slot gets `len(self._slots)` as its index, so insertion order becomes slot order.

The registry below the class is just as important as the class itself. `_session_stores` maps each `session_id` to a store instance, and `get_store()` lazily creates the store the first time a session touches memory. That pattern is why tests such as `mcp/tests/test_server.py` can prove that two sessions do not see each other's values.

```mermaid
flowchart TD
  A[session_id + key] --> B[get_store(session_id)]
  B --> C{Store exists?}
  C -->|No| D[Create PMMemoryStore]
  C -->|Yes| E[Reuse existing store]
  D --> F[peek or set]
  E --> F[peek or set]
  F --> G{Existing key?}
  G -->|Yes| H[Update value, keep index]
  G -->|No| I[Allocate next index]
```

## Basic Usage

```python
from pmll_memory_mcp import PMMemoryStore

store = PMMemoryStore(silo_size=4)
print(store.peek("page:/docs"))

slot = store.set("page:/docs", "<html>cached</html>")
print(slot)
print(store.peek("page:/docs"))
```

## Advanced Usage

This pattern mirrors how the server uses the store for isolated sessions.

```python
from pmll_memory_mcp.kv_store import get_store, drop_store

store_a = get_store("session-a", silo_size=8)
store_b = get_store("session-b", silo_size=8)

store_a.set("shared-key", "value-for-a")

print(store_a.peek("shared-key"))
print(store_b.peek("shared-key"))
print(drop_store("session-a"))
```

<Callout type="warn">`silo_size` is stored on the class, but the current implementation does not enforce a hard capacity. If you need bounded memory, you must add your own eviction policy instead of assuming the constructor argument will cap writes.</Callout>

<Accordions>
<Accordion title="Why stable slot indexes are useful">
The store preserves the original slot index when a key is updated. That matters because the code is modeling the older PMLL silo semantics rather than a generic dictionary cache. When you use the returned index in logs or diagnostics, the identity of the slot stays stable even if the payload changes. The trade-off is that the index is an implementation detail, not a durable external identifier, so you should not persist it across process restarts.
</Accordion>
<Accordion title="Why the store is simple instead of feature-rich">
The module does not implement TTL, LRU, or size-based eviction. That simplicity keeps the hot path small and predictable, and it matches how the server expects callers to use `flush()` at task completion. The downside is that long-running sessions can accumulate values indefinitely. If your application keeps one session open for a long time, add explicit lifecycle management around `flush()` or wrap the store with your own policy.
</Accordion>
</Accordions>
