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

Designed to improve context retention and retrieval for coding agents by combining:
    - Immediate context via KV cache (short-term)
    - Long-term knowledge via the SQLite-backed memory graph
    - Semantic search across both layers
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .kv_store import PMMemoryStore
from .memory_graph import (
    find_node_by_label,
    upsert_node,
    search_graph,
    get_graph_stats,
    NodeType,
)

# ---------------------------------------------------------------------------
# Promotion threshold: entries accessed >= this count get promoted
# ---------------------------------------------------------------------------
PROMOTION_THRESHOLD = 3

# Semantic fallback in resolve_context must reach this cosine score (0..1).
# Unrelated keys scored about 0.3-0.35 against small graphs in testing, so a
# lower bound of 0.5 turns those into misses. Exact label hits score 1.0.
MIN_SEMANTIC_SCORE = 0.5


def resolve_context(
    session_id: str,
    key: str,
    store: PMMemoryStore,
    min_score: Optional[float] = None,
) -> Dict[str, Any]:
    """Resolve context from both short-term and long-term memory layers.

    Order:
      1. Short-term KV exact key (``score`` 1.0, ``match`` "exact").
      2. Long-term graph node whose label equals ``key`` exactly
         (``score`` 1.0, ``match`` "exact").
      3. Long-term semantic search, accepted only when the top cosine score
         is at least ``min_score`` (default ``MIN_SEMANTIC_SCORE``);
         ``match`` is "semantic".
    Anything else is a miss, so a key that was never stored does not come
    back as an unrelated node.

    Returns:
        ``{"source": "short_term"|"long_term"|"miss", "value": str|None,
        "score": float, "match": "exact"|"semantic"|None, "node_id": str|None}``
    """
    threshold = MIN_SEMANTIC_SCORE if min_score is None else float(min_score)

    # Layer 1: Short-term KV cache
    hit, value, _index = store.peek(key)
    if hit and value is not None:
        return {"source": "short_term", "value": value, "score": 1.0, "match": "exact", "node_id": None}

    # Layer 2: Long-term graph, exact label
    node = find_node_by_label(session_id, key)
    if node is not None:
        return {"source": "long_term", "value": node.content, "score": 1.0, "match": "exact",
                "node_id": node.id}

    # Layer 3: Long-term graph, semantic search above the threshold
    graph_result = search_graph(session_id, key, max_depth=1, top_k=1)
    if graph_result.direct:
        top = graph_result.direct[0]
        score = top.relevance_score / 100.0
        if score >= threshold:
            return {"source": "long_term", "value": top.node.content, "score": score,
                    "match": "semantic", "node_id": top.node.id}

    return {"source": "miss", "value": None, "score": 0.0, "match": None, "node_id": None}


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
