---
title: "Cache Patterns"
description: "Implement the intended init → peek → set → flush short-term memory workflow."
---

This guide shows the core short-term pattern the repository is built around: initialize a session, check the cache before doing expensive work, populate the cache on a miss, and flush the session when the task is done.

<Steps>
<Step>

### Initialize the session

Using the Python tool wrappers keeps the example runnable as plain application code.

```python
from pmll_memory_mcp.server import init

session = init("agent-task-1", silo_size=32)
print(session)
```

</Step>
<Step>

### Check the cache before the expensive call

```python
from pmll_memory_mcp.server import peek

result = peek("agent-task-1", "https://example.com/pricing")
print(result)
```

</Step>
<Step>

### Run the expensive work only on a miss and persist the result

```python
from pmll_memory_mcp.server import peek, set

key = "https://example.com/pricing"
result = peek("agent-task-1", key)

if not result["hit"]:
    page_html = "<html>pricing page payload</html>"
    store_result = set("agent-task-1", key, page_html)
    print(store_result)

print(peek("agent-task-1", key))
```

</Step>
<Step>

### Flush the session at task completion

```python
from pmll_memory_mcp.server import flush

print(flush("agent-task-1"))
```

</Step>
</Steps>

## Complete Runnable Example

```python
from pmll_memory_mcp.server import init, peek, set, flush

session_id = "guide-cache"
init(session_id, silo_size=16)

key = "url:https://example.com/docs"
first = peek(session_id, key)
if not first["hit"]:
    payload = "rendered docs html"
    set(session_id, key, payload)

second = peek(session_id, key)
print(first)
print(second)
print(flush(session_id))
```

Expected output:

```text
{'hit': False}
{'hit': True, 'value': 'rendered docs html', 'index': 0}
{'status': 'flushed', 'cleared_count': 1}
```

## Why This Pattern Works

The implementation in `mcp/pmll_memory_mcp/peek.py` is intentionally narrow. It does not try to be a full cache framework. Instead, it gives you a safe gate in front of repeated work. That simplicity is why it is cheap enough to call before every expensive operation.

<Callout type="warn">Do not skip `flush()` in long-lived processes unless you also add explicit session cleanup. The source uses unbounded in-memory registries, so abandoned session IDs will hold onto memory until you clear them.</Callout>
