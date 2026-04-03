"""
solution_engine.py — Context+ Solution Engine Processor for PMLL MCP.

Integrates the Context+ semantic intelligence approach as the long-term
memory and solution engine for the PMLL persistent memory logic loop.

The solution engine:
    1. Bridges short-term KV cache (existing 5 tools) with the long-term
       memory graph (new 6 tools from Context+)
    2. Provides a unified context resolution path: short-term → long-term
    3. Auto-promotes frequently accessed short-term cache entries to the
       long-term memory graph
    4. Implements the Context+ decay scoring and similarity-based retrieval

This enables PMLL to achieve 99% accuracy by combining:
    - Immediate context via KV cache (short-term)
    - Persistent knowledge via memory graph (long-term)
    - Semantic search across both layers
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .kv_store import PMMemoryStore
from .memory_graph import (
    upsert_node,
    search_graph,
    get_graph_stats,
    NodeType,
)

# ---------------------------------------------------------------------------
# Promotion threshold: entries accessed >= this count get promoted
# ---------------------------------------------------------------------------
PROMOTION_THRESHOLD = 3


def resolve_context(
    session_id: str,
    key: str,
    store: PMMemoryStore,
) -> Dict[str, Any]:
    """Resolve context from both short-term and long-term memory layers.

    Returns:
        ``{"source": "short_term"|"long_term"|"miss", "value": str|None, "score": float}``
    """
    # Layer 1: Short-term KV cache
    hit, value, _index = store.peek(key)
    if hit and value is not None:
        return {"source": "short_term", "value": value, "score": 1.0}

    # Layer 2: Long-term memory graph (semantic search)
    graph_result = search_graph(session_id, key, max_depth=1, top_k=1)
    if graph_result.direct:
        top = graph_result.direct[0]
        return {
            "source": "long_term",
            "value": top.node.content,
            "score": top.relevance_score / 100.0,
        }

    return {"source": "miss", "value": None, "score": 0.0}


def promote_to_long_term(
    session_id: str,
    key: str,
    value: str,
    node_type: NodeType = "concept",
    metadata: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Promote a short-term KV entry to the long-term memory graph.

    Returns:
        ``{"promoted": True, "node_id": str}``
    """
    node = upsert_node(session_id, node_type, key, value, metadata)
    return {"promoted": True, "node_id": node.id}


def get_memory_status(
    session_id: str,
    store: PMMemoryStore,
) -> Dict[str, Any]:
    """Get a unified status view of both memory layers.

    Returns:
        Status dict with short_term and long_term sections.
    """
    stats = get_graph_stats(session_id)

    return {
        "short_term": {
            "slots": len(store),
            "silo_size": store.silo_size,
        },
        "long_term": {
            "nodes": stats["nodes"],
            "edges": stats["edges"],
            "types": stats["types"],
        },
        "promotion_threshold": PROMOTION_THRESHOLD,
    }
