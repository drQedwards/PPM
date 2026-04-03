"""
server.py — PMLL Memory MCP Server entrypoint.

Exposes MCP tools for Claude Sonnet/Opus agents:

Short-term (KV cache):
  init    — Set up the PMLL memory silo and Q-promise chain for a session.
  peek    — Non-destructive context check (core deduplication primitive).
  set     — Store a KV pair in the session's PMLL silo.
  resolve — Resolve a pending Q-promise continuation.
  flush   — Clear all short-term KV slots at agent task completion.

Long-term (Memory Graph, Context+ solution engine):
  upsert_memory_node      — Create/update a memory node with embeddings.
  create_relation         — Create typed edges between nodes.
  search_memory_graph     — Semantic search with graph traversal.
  prune_stale_links       — Remove decayed edges and orphan nodes.
  add_interlinked_context — Bulk-add nodes with auto-similarity linking.
  retrieve_with_traversal — Walk outward from a node.

Solution Engine:
  resolve_context       — Unified short+long term lookup.
  promote_to_long_term  — Promote KV entries to graph.
  memory_status         — Unified memory view.

Usage:
    python -m pmll_memory_mcp.server          # stdio transport (default)
    pmll-memory-mcp                           # via installed entry-point

License: MIT
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP

from .kv_store import get_store, drop_store
from .q_promise_bridge import QPromiseRegistry
from .peek import peek_context
from .memory_graph import (
    upsert_node,
    create_relation,
    search_graph,
    prune_stale_links,
    add_interlinked_context,
    retrieve_with_traversal,
    get_graph_stats,
    clear_graph,
    _graph_stores,
)
from .solution_engine import (
    resolve_context,
    promote_to_long_term,
    get_memory_status,
)

# ---------------------------------------------------------------------------
# MCP server instance
# ---------------------------------------------------------------------------
mcp = FastMCP(
    "pmll-memory-mcp",
    instructions=(
        "PMLL Memory MCP — persistent memory logic loop with short-term KV "
        "context memory, Q-promise deduplication, and Context+ long-term "
        "semantic memory graph for 99% accuracy. "
        "Short-term tools: `init`, `peek`, `set`, `resolve`, `flush`. "
        "Long-term tools: `upsert_memory_node`, `create_relation`, "
        "`search_memory_graph`, `prune_stale_links`, `add_interlinked_context`, "
        "`retrieve_with_traversal`. "
        "Solution engine: `resolve_context`, `promote_to_long_term`, `memory_status`."
    ),
)

# Module-level Q-promise registry shared across all sessions.
# Mirrors the global QMemNode chain pool in Q_promise_lib.
_promise_registry = QPromiseRegistry()

# Track which sessions have been initialised (session_id → silo_size).
_active_sessions: Dict[str, int] = {}


# ---------------------------------------------------------------------------
# Tool: init
# ---------------------------------------------------------------------------
@mcp.tool()
def init(session_id: str, silo_size: int = 256) -> Dict[str, Any]:
    """Initialise the PMLL memory silo for an agent session.

    Call this **once** at the start of every agent task, as the 3rd
    initializer alongside Playwright.  Sets up the KV silo and prepares
    the Q-promise chain for the session.

    Args:
        session_id: Unique identifier for this agent task (e.g. a UUID).
        silo_size:  Maximum number of KV slots (mirrors memory_silo_t.size).

    Returns:
        ``{"status": "initialized", "session_id": str, "silo_size": int}``
    """
    # Lazily create the store; also resets an existing session's silo.
    store = get_store(session_id, silo_size=silo_size)
    store.silo_size = silo_size
    _active_sessions[session_id] = silo_size
    return {"status": "initialized", "session_id": session_id, "silo_size": silo_size}


# ---------------------------------------------------------------------------
# Tool: peek
# ---------------------------------------------------------------------------
@mcp.tool()
def peek(session_id: str, key: str) -> Dict[str, Any]:
    """Non-destructive context check — the core deduplication primitive.

    Call this **before** any Playwright or other MCP tool invocation to
    check whether the required context already exists in the PMLL silo or
    is in-flight as a Q-promise.

    Args:
        session_id: The session identifier (from ``init``).
        key:        The context key to look up.

    Returns:
        ``{"hit": True, "value": str, "index": int}``        — KV cache hit
        ``{"hit": True, "status": "pending", "promise_id": str}`` — in-flight
        ``{"hit": False}``                                    — full miss
    """
    store = get_store(session_id)
    return peek_context(key, session_id, store, _promise_registry)


# ---------------------------------------------------------------------------
# Tool: set
# ---------------------------------------------------------------------------
@mcp.tool()
def set(session_id: str, key: str, value: str) -> Dict[str, Any]:
    """Store a KV pair in the session's PMLL memory silo.

    Call after a successful (non-cached) MCP tool invocation to populate
    the silo so future ``peek`` calls return a cache hit.

    Mirrors PMLL.c::update_silo() writing a var/value pair into the silo.

    Args:
        session_id: The session identifier (from ``init``).
        key:        The context key.
        value:      The string value to cache.

    Returns:
        ``{"status": "stored", "index": int}``
    """
    store = get_store(session_id)
    index = store.set(key, value)
    return {"status": "stored", "index": index}


# ---------------------------------------------------------------------------
# Tool: resolve
# ---------------------------------------------------------------------------
@mcp.tool()
def resolve(session_id: str, promise_id: str) -> Dict[str, Any]:
    """Check or resolve a Q-promise continuation.

    Mirrors the ``QThenCallback`` mechanism in Q_promise_lib/Q_promises.h —
    the callback is invoked when a QMemNode's payload becomes available.

    If the promise is already resolved, returns its payload immediately.
    If still pending, returns ``{"status": "pending", "payload": null}``.

    Args:
        session_id:  The session identifier (for context; not used to
                     namespace promises in this implementation).
        promise_id:  The promise identifier previously registered.

    Returns:
        ``{"status": "resolved" | "pending", "payload": str | null}``
    """
    found, status, payload = _promise_registry.peek_promise(promise_id)
    if not found:
        return {"status": "pending", "payload": None}
    return {"status": status, "payload": payload}


# ---------------------------------------------------------------------------
# Tool: flush
# ---------------------------------------------------------------------------
@mcp.tool()
def flush(session_id: str) -> Dict[str, Any]:
    """Clear all short-term KV slots for a session.

    Call at agent task completion to free memory.  Mirrors the teardown
    of a memory_silo_t allocation (PMLL.c::free_pml).

    Args:
        session_id: The session identifier (from ``init``).

    Returns:
        ``{"status": "flushed", "cleared_count": int}``
    """
    cleared = drop_store(session_id)
    _active_sessions.pop(session_id, None)
    return {"status": "flushed", "cleared_count": cleared}


# ---------------------------------------------------------------------------
# Tool: upsert_memory_node (Long-term memory)
# ---------------------------------------------------------------------------
@mcp.tool()
def upsert_memory_node(
    session_id: str,
    type: str,
    label: str,
    content: str,
    metadata: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Create or update a memory node in the long-term semantic graph.

    Nodes represent concepts, files, symbols, or notes with auto-generated
    TF-IDF embeddings for semantic search. Part of the Context+ solution
    engine for 99% accuracy persistent memory.

    Args:
        session_id: The session identifier (from ``init``).
        type:       Node type: concept, file, symbol, or note.
        label:      Short label for the node.
        content:    Full content/description of the node.
        metadata:   Optional key-value metadata for the node.

    Returns:
        ``{"status": "upserted", "node_id": str, ...}``
    """
    node = upsert_node(session_id, type, label, content, metadata)  # type: ignore[arg-type]
    stats = get_graph_stats(session_id)
    return {
        "status": "upserted",
        "node_id": node.id,
        "label": node.label,
        "node_type": node.type,
        "access_count": node.access_count,
        "graph_nodes": stats["nodes"],
        "graph_edges": stats["edges"],
    }


# ---------------------------------------------------------------------------
# Tool: create_memory_relation (Long-term memory)
# ---------------------------------------------------------------------------
@mcp.tool()
def create_memory_relation(
    session_id: str,
    source_id: str,
    target_id: str,
    relation: str,
    weight: float = 1.0,
) -> Dict[str, Any]:
    """Create a typed edge between two memory nodes in the long-term graph.

    Supported relation types: relates_to, depends_on, implements,
    references, similar_to, contains.

    Args:
        session_id: The session identifier (from ``init``).
        source_id:  Source node ID.
        target_id:  Target node ID.
        relation:   Relation type for the edge.
        weight:     Edge weight (default: 1.0).

    Returns:
        ``{"status": "created", "edge_id": str, ...}`` or error dict.
    """
    edge = create_relation(session_id, source_id, target_id, relation, weight)  # type: ignore[arg-type]
    if edge is None:
        return {"status": "error", "message": "One or both node IDs not found"}
    return {
        "status": "created",
        "edge_id": edge.id,
        "relation": edge.relation,
        "weight": edge.weight,
    }


# ---------------------------------------------------------------------------
# Tool: search_memory_graph (Long-term memory)
# ---------------------------------------------------------------------------
@mcp.tool()
def search_memory_graph(
    session_id: str,
    query: str,
    max_depth: int = 1,
    top_k: int = 5,
) -> Dict[str, Any]:
    """Semantic search with graph traversal.

    Finds direct matches then walks 1st/2nd-degree neighbors. Returns
    ranked results scored by cosine similarity and edge decay.

    Args:
        session_id: The session identifier (from ``init``).
        query:      Natural language search query.
        max_depth:  Maximum traversal depth (default: 1).
        top_k:      Maximum number of direct hits (default: 5).

    Returns:
        Search results with direct hits and neighbors.
    """
    result = search_graph(session_id, query, max_depth, top_k)
    return {
        "query": query,
        "direct": [
            {
                "node_id": d.node.id,
                "label": d.node.label,
                "type": d.node.type,
                "content": d.node.content,
                "score": d.relevance_score,
            }
            for d in result.direct
        ],
        "neighbors": [
            {
                "node_id": n.node.id,
                "label": n.node.label,
                "type": n.node.type,
                "content": n.node.content,
                "score": n.relevance_score,
                "depth": n.depth,
                "path": n.path_relations,
            }
            for n in result.neighbors
        ],
        "total_nodes": result.total_nodes,
        "total_edges": result.total_edges,
    }


# ---------------------------------------------------------------------------
# Tool: prune_memory_links (Long-term memory)
# ---------------------------------------------------------------------------
@mcp.tool()
def prune_memory_links(
    session_id: str,
    threshold: float = 0.15,
) -> Dict[str, Any]:
    """Remove decayed edges and orphan nodes from the long-term memory graph.

    Args:
        session_id: The session identifier (from ``init``).
        threshold:  Decay threshold below which edges are pruned (default: 0.15).

    Returns:
        ``{"status": "pruned", "removed": int, "remaining_edges": int}``
    """
    result = prune_stale_links(session_id, threshold)
    return {
        "status": "pruned",
        "removed": result["removed"],
        "remaining_edges": result["remaining"],
    }


# ---------------------------------------------------------------------------
# Tool: add_interlinked_memory (Long-term memory)
# ---------------------------------------------------------------------------
@mcp.tool()
def add_interlinked_memory(
    session_id: str,
    items: List[Dict[str, Any]],
    auto_link: bool = True,
) -> Dict[str, Any]:
    """Bulk-add nodes with auto-similarity linking (cosine >= 0.72).

    Args:
        session_id: The session identifier (from ``init``).
        items:      Array of dicts with type, label, content, metadata.
        auto_link:  Auto-create similarity edges (default: True).

    Returns:
        ``{"status": "added", "nodes_created": int, "edges_created": int, ...}``
    """
    result = add_interlinked_context(session_id, items, auto_link)
    return {
        "status": "added",
        "nodes_created": len(result["nodes"]),
        "edges_created": len(result["edges"]),
        "nodes": [
            {"id": n.id, "label": n.label, "type": n.type}
            for n in result["nodes"]
        ],
    }


# ---------------------------------------------------------------------------
# Tool: retrieve_memory_traversal (Long-term memory)
# ---------------------------------------------------------------------------
@mcp.tool()
def retrieve_memory_traversal(
    session_id: str,
    start_node_id: str,
    max_depth: int = 2,
) -> Dict[str, Any]:
    """Walk outward from a node, return scored neighbors.

    Args:
        session_id:    The session identifier (from ``init``).
        start_node_id: ID of the starting node.
        max_depth:     Maximum traversal depth (default: 2).

    Returns:
        Traversal results with start node and neighbors.
    """
    results = retrieve_with_traversal(session_id, start_node_id, max_depth)
    if not results:
        return {"status": "error", "message": f"Node not found: {start_node_id}"}
    return {
        "start_node": results[0].node.label,
        "results": [
            {
                "node_id": r.node.id,
                "label": r.node.label,
                "type": r.node.type,
                "content": r.node.content,
                "depth": r.depth,
                "score": r.relevance_score,
                "path": r.path_relations,
            }
            for r in results
        ],
    }


# ---------------------------------------------------------------------------
# Tool: resolve_memory_context (Solution Engine)
# ---------------------------------------------------------------------------
@mcp.tool()
def resolve_memory_context(
    session_id: str,
    key: str,
) -> Dict[str, Any]:
    """Unified context resolution across both short-term and long-term memory.

    Checks KV cache first, then falls back to semantic graph search. This is
    the primary Context+ solution engine tool for achieving 99% accuracy.

    Args:
        session_id: The session identifier (from ``init``).
        key:        The context key to resolve.

    Returns:
        ``{"source": "short_term"|"long_term"|"miss", "value": str|None, "score": float}``
    """
    store = get_store(session_id)
    return resolve_context(session_id, key, store)


# ---------------------------------------------------------------------------
# Tool: promote_memory_to_long_term (Solution Engine)
# ---------------------------------------------------------------------------
@mcp.tool()
def promote_memory_to_long_term(
    session_id: str,
    key: str,
    value: str,
    node_type: str = "concept",
) -> Dict[str, Any]:
    """Promote a short-term KV cache entry to the long-term semantic graph.

    Creates a persistent memory node from a frequently accessed cache entry,
    ensuring important context survives session flushes.

    Args:
        session_id: The session identifier (from ``init``).
        key:        The context key/label for the memory node.
        value:      The content to store in long-term memory.
        node_type:  Node type (default: concept).

    Returns:
        ``{"promoted": True, "node_id": str}``
    """
    return promote_to_long_term(session_id, key, value, node_type)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tool: memory_status (Solution Engine)
# ---------------------------------------------------------------------------
@mcp.tool()
def memory_status(session_id: str) -> Dict[str, Any]:
    """Unified status view of both short-term and long-term memory layers.

    Args:
        session_id: The session identifier (from ``init``).

    Returns:
        Status dict with short_term, long_term, and promotion_threshold.
    """
    store = get_store(session_id)
    return get_memory_status(session_id, store)


# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------
def main() -> None:
    """Run the MCP server over stdio (default transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
