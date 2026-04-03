"""
memory_graph.py — In-memory property graph for long-term context memory.

Adapted from Context+ (github.com/drQedwards/contextplus) memory-graph.ts.
Provides a persistent memory graph with typed nodes, weighted edges, decay
scoring, and graph traversal for the PMLL MCP solution engine.

Architecture:
    - Nodes: concept, file, symbol, note — each with TF-IDF embeddings
    - Edges: typed relations with temporal decay (e^(-λt))
    - Search: cosine similarity + graph neighbor traversal
    - Persistence: JSON serialization to session-level storage

The graph serves as the long-term memory layer complementing the existing
short-term KV store (init/peek/set/resolve/flush tools).
"""

from __future__ import annotations

import math
import random
import string
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Tuple

from .embeddings import embed, cosine_similarity

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

NodeType = Literal["concept", "file", "symbol", "note"]
RelationType = Literal[
    "relates_to", "depends_on", "implements", "references", "similar_to", "contains"
]


@dataclass
class MemoryNode:
    """A node in the memory graph."""

    id: str
    type: NodeType
    label: str
    content: str
    embedding: List[float]
    created_at: float
    last_accessed: float
    access_count: int
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class MemoryEdge:
    """A typed edge in the memory graph."""

    id: str
    source: str
    target: str
    relation: RelationType
    weight: float
    created_at: float
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class TraversalResult:
    """Result of a graph traversal."""

    node: MemoryNode
    depth: int
    path_relations: List[str]
    relevance_score: float


@dataclass
class GraphSearchResult:
    """Result of a graph search."""

    direct: List[TraversalResult]
    neighbors: List[TraversalResult]
    total_nodes: int
    total_edges: int


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DECAY_LAMBDA = 0.05
SIMILARITY_THRESHOLD = 0.72
STALE_THRESHOLD = 0.15

# ---------------------------------------------------------------------------
# Graph store
# ---------------------------------------------------------------------------


class _GraphStore:
    """Internal graph store for nodes and edges."""

    def __init__(self) -> None:
        self.nodes: Dict[str, MemoryNode] = {}
        self.edges: Dict[str, MemoryEdge] = {}


# Session-scoped graph registry
_graph_stores: Dict[str, _GraphStore] = {}


def _generate_id(prefix: str) -> str:
    """Generate a unique ID with prefix."""
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"{prefix}-{int(time.time() * 1000)}-{suffix}"


def _get_graph(session_id: str) -> _GraphStore:
    """Get or create graph store for a session."""
    if session_id not in _graph_stores:
        _graph_stores[session_id] = _GraphStore()
    return _graph_stores[session_id]


def _decay_weight(edge: MemoryEdge) -> float:
    """Compute decayed edge weight: w * e^(-λ*days)."""
    days_since = (time.time() - edge.created_at) / 86400.0
    return edge.weight * math.exp(-DECAY_LAMBDA * days_since)


def _get_edges_for_node(graph: _GraphStore, node_id: str) -> List[MemoryEdge]:
    """Get all edges connected to a node."""
    return [
        e for e in graph.edges.values()
        if e.source == node_id or e.target == node_id
    ]


def _get_neighbor_id(edge: MemoryEdge, from_id: str) -> str:
    """Get the other end of an edge."""
    return edge.target if edge.source == from_id else edge.source


# ---------------------------------------------------------------------------
# Core graph operations
# ---------------------------------------------------------------------------


def upsert_node(
    session_id: str,
    node_type: NodeType,
    label: str,
    content: str,
    metadata: Optional[Dict[str, str]] = None,
) -> MemoryNode:
    """Create or update a memory node in the session graph."""
    graph = _get_graph(session_id)

    for node in graph.nodes.values():
        if node.label == label and node.type == node_type:
            node.content = content
            node.last_accessed = time.time()
            node.access_count += 1
            if metadata:
                node.metadata.update(metadata)
            node.embedding = embed(f"{label} {content}")
            return node

    node = MemoryNode(
        id=_generate_id("mn"),
        type=node_type,
        label=label,
        content=content,
        embedding=embed(f"{label} {content}"),
        created_at=time.time(),
        last_accessed=time.time(),
        access_count=1,
        metadata=metadata or {},
    )
    graph.nodes[node.id] = node
    return node


def create_relation(
    session_id: str,
    source_id: str,
    target_id: str,
    relation: RelationType,
    weight: Optional[float] = None,
    metadata: Optional[Dict[str, str]] = None,
) -> Optional[MemoryEdge]:
    """Create a typed edge between two nodes."""
    graph = _get_graph(session_id)
    if source_id not in graph.nodes or target_id not in graph.nodes:
        return None

    for edge in graph.edges.values():
        if (
            edge.source == source_id
            and edge.target == target_id
            and edge.relation == relation
        ):
            if weight is not None:
                edge.weight = weight
            if metadata:
                edge.metadata.update(metadata)
            return edge

    edge = MemoryEdge(
        id=_generate_id("me"),
        source=source_id,
        target=target_id,
        relation=relation,
        weight=weight if weight is not None else 1.0,
        created_at=time.time(),
        metadata=metadata or {},
    )
    graph.edges[edge.id] = edge
    return edge


def search_graph(
    session_id: str,
    query: str,
    max_depth: int = 1,
    top_k: int = 5,
    edge_filter: Optional[List[RelationType]] = None,
) -> GraphSearchResult:
    """Semantic search with graph traversal."""
    graph = _get_graph(session_id)
    nodes = list(graph.nodes.values())
    if not nodes:
        return GraphSearchResult(direct=[], neighbors=[], total_nodes=0, total_edges=0)

    query_vec = embed(query)
    scored = sorted(
        [(n, cosine_similarity(query_vec, n.embedding)) for n in nodes],
        key=lambda x: x[1],
        reverse=True,
    )

    direct_hits: List[TraversalResult] = []
    for node, score in scored[:top_k]:
        node.last_accessed = time.time()
        direct_hits.append(
            TraversalResult(
                node=node,
                depth=0,
                path_relations=[],
                relevance_score=round(score * 100, 1),
            )
        )

    neighbor_results: List[TraversalResult] = []
    visited = {h.node.id for h in direct_hits}

    for hit in direct_hits:
        _traverse_neighbors(
            graph, hit.node.id, query_vec, 1, max_depth,
            [hit.node.label], visited, neighbor_results, edge_filter,
        )

    neighbor_results.sort(key=lambda r: r.relevance_score, reverse=True)

    return GraphSearchResult(
        direct=direct_hits,
        neighbors=neighbor_results[: top_k * 2],
        total_nodes=len(nodes),
        total_edges=len(graph.edges),
    )


def _traverse_neighbors(
    graph: _GraphStore,
    node_id: str,
    query_vec: List[float],
    depth: int,
    max_depth: int,
    path_labels: List[str],
    visited: set,
    results: List[TraversalResult],
    edge_filter: Optional[List[RelationType]],
) -> None:
    """Recursively traverse neighbors."""
    if depth > max_depth:
        return

    for edge in _get_edges_for_node(graph, node_id):
        if edge_filter and edge.relation not in edge_filter:
            continue
        neighbor_id = _get_neighbor_id(edge, node_id)
        if neighbor_id in visited:
            continue

        neighbor = graph.nodes.get(neighbor_id)
        if not neighbor:
            continue

        visited.add(neighbor_id)
        similarity = cosine_similarity(query_vec, neighbor.embedding)
        edge_decay = _decay_weight(edge)
        relevance = similarity * 0.6 + (edge_decay / max(edge.weight, 0.01)) * 0.4

        results.append(
            TraversalResult(
                node=neighbor,
                depth=depth,
                path_relations=[*path_labels, f"--[{edge.relation}]-->", neighbor.label],
                relevance_score=round(relevance * 100, 1),
            )
        )

        neighbor.last_accessed = time.time()
        _traverse_neighbors(
            graph, neighbor_id, query_vec, depth + 1, max_depth,
            [*path_labels, f"--[{edge.relation}]-->", neighbor.label],
            visited, results, edge_filter,
        )


def prune_stale_links(
    session_id: str,
    threshold: Optional[float] = None,
) -> Dict[str, int]:
    """Remove decayed edges and orphan nodes."""
    graph = _get_graph(session_id)
    cutoff = threshold if threshold is not None else STALE_THRESHOLD
    to_remove: List[str] = []

    for edge_id, edge in graph.edges.items():
        if _decay_weight(edge) < cutoff:
            to_remove.append(edge_id)

    for eid in to_remove:
        del graph.edges[eid]

    orphans = [
        nid
        for nid, node in graph.nodes.items()
        if (
            not _get_edges_for_node(graph, nid)
            and node.access_count <= 1
            and time.time() - node.last_accessed > 7 * 86400
        )
    ]
    for nid in orphans:
        del graph.nodes[nid]

    return {"removed": len(to_remove) + len(orphans), "remaining": len(graph.edges)}


def add_interlinked_context(
    session_id: str,
    items: List[Dict[str, Any]],
    auto_link: bool = True,
) -> Dict[str, Any]:
    """Bulk-add nodes with auto-similarity linking (cosine ≥ 0.72)."""
    created_nodes: List[MemoryNode] = []
    for item in items:
        created_nodes.append(
            upsert_node(
                session_id,
                item["type"],
                item["label"],
                item["content"],
                item.get("metadata"),
            )
        )

    created_edges: List[MemoryEdge] = []

    if auto_link and len(created_nodes) > 1:
        for i in range(len(created_nodes)):
            for j in range(i + 1, len(created_nodes)):
                similarity = cosine_similarity(
                    created_nodes[i].embedding, created_nodes[j].embedding
                )
                if similarity >= SIMILARITY_THRESHOLD:
                    edge = create_relation(
                        session_id,
                        created_nodes[i].id,
                        created_nodes[j].id,
                        "similar_to",
                        similarity,
                    )
                    if edge:
                        created_edges.append(edge)

    graph = _get_graph(session_id)
    created_ids = {n.id for n in created_nodes}
    existing_nodes = [n for n in graph.nodes.values() if n.id not in created_ids][:200]

    if auto_link:
        for new_node in created_nodes:
            for existing in existing_nodes:
                similarity = cosine_similarity(new_node.embedding, existing.embedding)
                if similarity >= SIMILARITY_THRESHOLD:
                    edge = create_relation(
                        session_id, new_node.id, existing.id, "similar_to", similarity
                    )
                    if edge:
                        created_edges.append(edge)

    return {"nodes": created_nodes, "edges": created_edges}


def retrieve_with_traversal(
    session_id: str,
    start_node_id: str,
    max_depth: int = 2,
    edge_filter: Optional[List[RelationType]] = None,
) -> List[TraversalResult]:
    """Walk outward from a node, return scored neighbors."""
    graph = _get_graph(session_id)
    start_node = graph.nodes.get(start_node_id)
    if not start_node:
        return []

    start_node.last_accessed = time.time()
    start_node.access_count += 1

    results: List[TraversalResult] = [
        TraversalResult(
            node=start_node,
            depth=0,
            path_relations=[start_node.label],
            relevance_score=100.0,
        )
    ]

    visited = {start_node_id}
    _collect_traversal(
        graph, start_node_id, 1, max_depth, [start_node.label],
        visited, results, edge_filter,
    )

    return results


def _collect_traversal(
    graph: _GraphStore,
    node_id: str,
    depth: int,
    max_depth: int,
    path_labels: List[str],
    visited: set,
    results: List[TraversalResult],
    edge_filter: Optional[List[RelationType]],
) -> None:
    """Collect traversal results recursively."""
    if depth > max_depth:
        return

    for edge in _get_edges_for_node(graph, node_id):
        if edge_filter and edge.relation not in edge_filter:
            continue
        neighbor_id = _get_neighbor_id(edge, node_id)
        if neighbor_id in visited:
            continue

        neighbor = graph.nodes.get(neighbor_id)
        if not neighbor:
            continue

        visited.add(neighbor_id)
        neighbor.last_accessed = time.time()

        decayed = _decay_weight(edge)
        depth_penalty = 1 / (1 + depth * 0.3)
        score = decayed * depth_penalty * 100

        results.append(
            TraversalResult(
                node=neighbor,
                depth=depth,
                path_relations=[*path_labels, f"--[{edge.relation}]-->", neighbor.label],
                relevance_score=round(score, 1),
            )
        )

        _collect_traversal(
            graph, neighbor_id, depth + 1, max_depth,
            [*path_labels, f"--[{edge.relation}]-->", neighbor.label],
            visited, results, edge_filter,
        )


def get_graph_stats(session_id: str) -> Dict[str, Any]:
    """Get summary statistics for the session's memory graph."""
    graph = _get_graph(session_id)
    types: Dict[str, int] = {}
    relations: Dict[str, int] = {}

    for node in graph.nodes.values():
        types[node.type] = types.get(node.type, 0) + 1
    for edge in graph.edges.values():
        relations[edge.relation] = relations.get(edge.relation, 0) + 1

    return {
        "nodes": len(graph.nodes),
        "edges": len(graph.edges),
        "types": types,
        "relations": relations,
    }


def clear_graph(session_id: str) -> int:
    """Clear the graph for a session."""
    graph = _graph_stores.get(session_id)
    if not graph:
        return 0
    count = len(graph.nodes) + len(graph.edges)
    del _graph_stores[session_id]
    return count
