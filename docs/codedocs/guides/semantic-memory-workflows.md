---
title: "Semantic Memory Workflows"
description: "Build a hybrid workflow that writes to the graph, links nodes, searches semantically, and resolves context."
---

This guide covers a realistic workflow for the long-term layer: ingest related knowledge, connect it, search it semantically, and then use the solution engine as the stable read API.

<Steps>
<Step>

### Seed a session graph

```python
from pmll_memory_mcp import upsert_node, create_relation

session_id = "workflow"

api = upsert_node(session_id, "file", "api.py", "Defines the public HTTP client")
auth = upsert_node(session_id, "symbol", "authenticate", "Creates and refreshes tokens")
docs = upsert_node(session_id, "note", "auth docs", "Login, refresh, and token storage guidance")

create_relation(session_id, api.id, auth.id, "contains")
create_relation(session_id, auth.id, docs.id, "references")
```

</Step>
<Step>

### Add a batch of related context

```python
from pmll_memory_mcp import add_interlinked_context

add_interlinked_context(
    session_id,
    [
        {"type": "concept", "label": "token refresh", "content": "Rotates expired access tokens"},
        {"type": "concept", "label": "session cache", "content": "Stores fresh auth responses for one task"},
    ],
    auto_link=True,
)
```

</Step>
<Step>

### Search semantically and inspect neighbors

```python
from pmll_memory_mcp import search_graph, retrieve_with_traversal

search = search_graph(session_id, "how do tokens refresh", max_depth=1, top_k=3)
top = search.direct[0]

print(top.node.label, top.relevance_score)
for item in retrieve_with_traversal(session_id, top.node.id, max_depth=2):
    print(item.depth, item.node.label, item.path_relations)
```

</Step>
<Step>

### Promote and resolve through the solution engine

```python
from pmll_memory_mcp import PMMemoryStore, promote_to_long_term, resolve_context

store = PMMemoryStore()
store.set("auth-response", "fresh login payload")

promote_to_long_term(session_id, "auth-response", "fresh login payload", "note")
print(resolve_context(session_id, "token refresh", store))
```

</Step>
</Steps>

## Complete Runnable Example

```python
from pmll_memory_mcp import (
    PMMemoryStore,
    upsert_node,
    create_relation,
    search_graph,
    promote_to_long_term,
    resolve_context,
)

session_id = "semantic-guide"
store = PMMemoryStore()

node_a = upsert_node(session_id, "concept", "billing", "Tracks invoices and usage")
node_b = upsert_node(session_id, "concept", "receipts", "Stores payment receipts")
create_relation(session_id, node_a.id, node_b.id, "relates_to")

store.set("billing-cache", "latest billing summary")
promote_to_long_term(session_id, "billing-cache", "latest billing summary", "note")

result = search_graph(session_id, "payment usage")
print(result.direct[0].node.label)
print(resolve_context(session_id, "billing-cache", store))
```

## When To Use This Pattern

Use this workflow when you need memory that survives a single task and remains queryable by meaning, not just by exact key. The source design makes it especially useful for codebase notes, tool outputs, and cross-step summaries.

<Callout type="warn">Search quality depends heavily on the descriptive quality of `label` and `content`. If you only store opaque IDs or one-word fragments, TF-IDF similarity will be weak and auto-linking will be noisy.</Callout>
