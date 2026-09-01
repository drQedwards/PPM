"""
memory_graph.py — SQLite-backed property graph for long-term context memory.

Adapted from Context+ (github.com/drQedwards/contextplus) memory-graph.ts.
Designed to improve context retention and retrieval for coding agents.

Architecture:
    - Nodes: concept, file, symbol, note — each with persisted hashing embeddings
    - Edges: typed relations with temporal decay (e^(-λt))
    - Search: cosine similarity + graph neighbor traversal
    - Persistence: SQLite (session_id → durable namespace). JSON for export/dev only.

Process restart reloads the graph from SQLite. Stores are process-local;
MCP assumes single-threaded / externally serialized access, with an RLock
around registry + DB writes.
"""

from __future__ import annotations

import json
import math
import os
import random
import sqlite3
import string
import tempfile
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

from .embeddings import embed, cosine_similarity

NodeType = Literal["concept", "file", "symbol", "note"]
RelationType = Literal[
    "relates_to", "depends_on", "implements", "references", "similar_to", "contains"
]


@dataclass
class MemoryNode:
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
    id: str
    source: str
    target: str
    relation: RelationType
    weight: float
    created_at: float
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class TraversalResult:
    node: MemoryNode
    depth: int
    path_relations: List[str]
    relevance_score: float


@dataclass
class GraphSearchResult:
    direct: List[TraversalResult]
    neighbors: List[TraversalResult]
    total_nodes: int
    total_edges: int


DECAY_LAMBDA = 0.05
SIMILARITY_THRESHOLD = 0.72
STALE_THRESHOLD = 0.15

_SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    session_id   TEXT NOT NULL,
    id           TEXT NOT NULL,
    type         TEXT NOT NULL,
    label        TEXT NOT NULL,
    content      TEXT NOT NULL,
    embedding    TEXT NOT NULL,
    created_at   REAL NOT NULL,
    last_accessed REAL NOT NULL,
    access_count INTEGER NOT NULL,
    metadata     TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (session_id, id)
);
CREATE TABLE IF NOT EXISTS edges (
    session_id TEXT NOT NULL,
    id         TEXT NOT NULL,
    source     TEXT NOT NULL,
    target     TEXT NOT NULL,
    relation   TEXT NOT NULL,
    weight     REAL NOT NULL,
    created_at REAL NOT NULL,
    metadata   TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (session_id, id)
);
CREATE INDEX IF NOT EXISTS idx_nodes_session ON nodes(session_id);
CREATE INDEX IF NOT EXISTS idx_edges_session ON edges(session_id);
"""

_lock = threading.RLock()
_db_path: Optional[str] = None
_db_conn: Optional[sqlite3.Connection] = None


class _GraphStore:
    def __init__(self) -> None:
        self.nodes: Dict[str, MemoryNode] = {}
        self.edges: Dict[str, MemoryEdge] = {}
        self.loaded: bool = False


_graph_stores: Dict[str, _GraphStore] = {}


def _default_db_path() -> str:
    env = os.environ.get("PMLL_GRAPH_DB")
    if env:
        return env
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(
        os.path.expanduser("~"), ".local", "share", "pmll"
    )
    try:
        os.makedirs(base, exist_ok=True)
        return os.path.join(base, "memory_graph.sqlite3")
    except OSError:
        return os.path.join(tempfile.gettempdir(), "pmll_memory_graph.sqlite3")


def configure_db(path: Optional[str] = None) -> str:
    """Set (or reset) the SQLite database path and open a connection."""
    global _db_path, _db_conn
    with _lock:
        if _db_conn is not None:
            try:
                _db_conn.close()
            except sqlite3.Error:
                pass
            _db_conn = None
        _graph_stores.clear()
        _db_path = path if path is not None else _default_db_path()
        parent = os.path.dirname(_db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        _db_conn = sqlite3.connect(_db_path, check_same_thread=False)
        _db_conn.row_factory = sqlite3.Row
        _db_conn.executescript(_SCHEMA)
        _db_conn.commit()
        return _db_path


def get_db_path() -> str:
    with _lock:
        if _db_conn is None or _db_path is None:
            configure_db()
        assert _db_path is not None
        return _db_path


def _conn() -> sqlite3.Connection:
    with _lock:
        if _db_conn is None:
            configure_db()
        assert _db_conn is not None
        return _db_conn


def _generate_id(prefix: str) -> str:
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"{prefix}-{int(time.time() * 1000)}-{suffix}"


def _row_to_node(row: sqlite3.Row) -> MemoryNode:
    return MemoryNode(
        id=row["id"],
        type=row["type"],  # type: ignore[arg-type]
        label=row["label"],
        content=row["content"],
        embedding=json.loads(row["embedding"]),
        created_at=row["created_at"],
        last_accessed=row["last_accessed"],
        access_count=row["access_count"],
        metadata=json.loads(row["metadata"] or "{}"),
    )


def _row_to_edge(row: sqlite3.Row) -> MemoryEdge:
    return MemoryEdge(
        id=row["id"],
        source=row["source"],
        target=row["target"],
        relation=row["relation"],  # type: ignore[arg-type]
        weight=row["weight"],
        created_at=row["created_at"],
        metadata=json.loads(row["metadata"] or "{}"),
    )


def _persist_node(session_id: str, node: MemoryNode) -> None:
    _conn().execute(
        """
        INSERT OR REPLACE INTO nodes
        (session_id, id, type, label, content, embedding, created_at,
         last_accessed, access_count, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id, node.id, node.type, node.label, node.content,
            json.dumps(node.embedding), node.created_at, node.last_accessed,
            node.access_count, json.dumps(node.metadata),
        ),
    )
    _conn().commit()


def _persist_edge(session_id: str, edge: MemoryEdge) -> None:
    _conn().execute(
        """
        INSERT OR REPLACE INTO edges
        (session_id, id, source, target, relation, weight, created_at, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id, edge.id, edge.source, edge.target, edge.relation,
            edge.weight, edge.created_at, json.dumps(edge.metadata),
        ),
    )
    _conn().commit()


def _delete_edge_ids(session_id: str, edge_ids: List[str]) -> None:
    if not edge_ids:
        return
    _conn().executemany(
        "DELETE FROM edges WHERE session_id = ? AND id = ?",
        [(session_id, eid) for eid in edge_ids],
    )
    _conn().commit()


def _delete_node_ids(session_id: str, node_ids: List[str]) -> None:
    if not node_ids:
        return
    _conn().executemany(
        "DELETE FROM nodes WHERE session_id = ? AND id = ?",
        [(session_id, nid) for nid in node_ids],
    )
    _conn().commit()


def _load_session(session_id: str, graph: _GraphStore) -> None:
    cur = _conn().execute("SELECT * FROM nodes WHERE session_id = ?", (session_id,))
    for row in cur.fetchall():
        node = _row_to_node(row)
        graph.nodes[node.id] = node
    cur = _conn().execute("SELECT * FROM edges WHERE session_id = ?", (session_id,))
    for row in cur.fetchall():
        edge = _row_to_edge(row)
        graph.edges[edge.id] = edge
    graph.loaded = True


def _get_graph(session_id: str) -> _GraphStore:
    with _lock:
        if session_id not in _graph_stores:
            _graph_stores[session_id] = _GraphStore()
        graph = _graph_stores[session_id]
        if not graph.loaded:
            _load_session(session_id, graph)
        return graph


def _decay_weight(edge: MemoryEdge) -> float:
    days_since = (time.time() - edge.created_at) / 86400.0
    return edge.weight * math.exp(-DECAY_LAMBDA * days_since)


def _get_edges_for_node(graph: _GraphStore, node_id: str) -> List[MemoryEdge]:
    return [e for e in graph.edges.values() if e.source == node_id or e.target == node_id]


def _get_neighbor_id(edge: MemoryEdge, from_id: str) -> str:
    return edge.target if edge.source == from_id else edge.source


def upsert_node(
    session_id: str,
    node_type: NodeType,
    label: str,
    content: str,
    metadata: Optional[Dict[str, str]] = None,
) -> MemoryNode:
    with _lock:
        graph = _get_graph(session_id)
        for node in graph.nodes.values():
            if node.label == label and node.type == node_type:
                node.content = content
                node.last_accessed = time.time()
                node.access_count += 1
                if metadata:
                    node.metadata.update(metadata)
                node.embedding = embed(f"{label} {content}")
                _persist_node(session_id, node)
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
        _persist_node(session_id, node)
        return node


def create_relation(
    session_id: str,
    source_id: str,
    target_id: str,
    relation: RelationType,
    weight: Optional[float] = None,
    metadata: Optional[Dict[str, str]] = None,
) -> Optional[MemoryEdge]:
    with _lock:
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
                _persist_edge(session_id, edge)
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
        _persist_edge(session_id, edge)
        return edge


def search_graph(
    session_id: str,
    query: str,
    max_depth: int = 1,
    top_k: int = 5,
    edge_filter: Optional[List[RelationType]] = None,
) -> GraphSearchResult:
    with _lock:
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
            _persist_node(session_id, node)
            direct_hits.append(
                TraversalResult(
                    node=node, depth=0, path_relations=[],
                    relevance_score=round(score * 100, 1),
                )
            )
        neighbor_results: List[TraversalResult] = []
        visited = {h.node.id for h in direct_hits}
        for hit in direct_hits:
            _traverse_neighbors(
                graph, session_id, hit.node.id, query_vec, 1, max_depth,
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
    session_id: str,
    node_id: str,
    query_vec: List[float],
    depth: int,
    max_depth: int,
    path_labels: List[str],
    visited: set,
    results: List[TraversalResult],
    edge_filter: Optional[List[RelationType]],
) -> None:
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
        _persist_node(session_id, neighbor)
        _traverse_neighbors(
            graph, session_id, neighbor_id, query_vec, depth + 1, max_depth,
            [*path_labels, f"--[{edge.relation}]-->", neighbor.label],
            visited, results, edge_filter,
        )


def prune_stale_links(
    session_id: str,
    threshold: Optional[float] = None,
) -> Dict[str, int]:
    with _lock:
        graph = _get_graph(session_id)
        cutoff = threshold if threshold is not None else STALE_THRESHOLD
        to_remove = [eid for eid, edge in graph.edges.items() if _decay_weight(edge) < cutoff]
        for eid in to_remove:
            del graph.edges[eid]
        _delete_edge_ids(session_id, to_remove)
        orphans = [
            nid for nid, node in graph.nodes.items()
            if (
                not _get_edges_for_node(graph, nid)
                and node.access_count <= 1
                and time.time() - node.last_accessed > 7 * 86400
            )
        ]
        for nid in orphans:
            del graph.nodes[nid]
        _delete_node_ids(session_id, orphans)
        return {"removed": len(to_remove) + len(orphans), "remaining": len(graph.edges)}


def add_interlinked_context(
    session_id: str,
    items: List[Dict[str, Any]],
    auto_link: bool = True,
) -> Dict[str, Any]:
    created_nodes: List[MemoryNode] = []
    for item in items:
        created_nodes.append(
            upsert_node(
                session_id, item["type"], item["label"], item["content"], item.get("metadata"),
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
                        session_id, created_nodes[i].id, created_nodes[j].id,
                        "similar_to", similarity,
                    )
                    if edge:
                        created_edges.append(edge)
    with _lock:
        graph = _get_graph(session_id)
        existing_nodes = [
            n for n in graph.nodes.values()
            if n.id not in {cn.id for cn in created_nodes}
        ][:200]
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
    with _lock:
        graph = _get_graph(session_id)
        start_node = graph.nodes.get(start_node_id)
        if not start_node:
            return []
        start_node.last_accessed = time.time()
        start_node.access_count += 1
        _persist_node(session_id, start_node)
        results: List[TraversalResult] = [
            TraversalResult(
                node=start_node, depth=0,
                path_relations=[start_node.label], relevance_score=100,
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
                node=neighbor, depth=depth,
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
    with _lock:
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
            "db_path": get_db_path(),
        }


def export_graph(session_id: str) -> Dict[str, Any]:
    """Export session graph as JSON-serializable dict (dev/export only)."""
    with _lock:
        graph = _get_graph(session_id)
        return {
            "nodes": {
                nid: {
                    "id": n.id, "type": n.type, "label": n.label, "content": n.content,
                    "embedding": n.embedding, "created_at": n.created_at,
                    "last_accessed": n.last_accessed, "access_count": n.access_count,
                    "metadata": n.metadata,
                }
                for nid, n in graph.nodes.items()
            },
            "edges": {
                eid: {
                    "id": e.id, "source": e.source, "target": e.target,
                    "relation": e.relation, "weight": e.weight,
                    "created_at": e.created_at, "metadata": e.metadata,
                }
                for eid, e in graph.edges.items()
            },
        }


def import_graph(session_id: str, data: Dict[str, Any]) -> None:
    with _lock:
        clear_graph(session_id)
        graph = _get_graph(session_id)
        for raw in (data.get("nodes") or {}).values():
            node = MemoryNode(
                id=raw["id"], type=raw["type"], label=raw["label"], content=raw["content"],
                embedding=list(raw.get("embedding") or embed(f"{raw['label']} {raw['content']}")),
                created_at=raw.get("created_at", time.time()),
                last_accessed=raw.get("last_accessed", time.time()),
                access_count=raw.get("access_count", 1),
                metadata=dict(raw.get("metadata") or {}),
            )
            graph.nodes[node.id] = node
            _persist_node(session_id, node)
        for raw in (data.get("edges") or {}).values():
            edge = MemoryEdge(
                id=raw["id"], source=raw["source"], target=raw["target"],
                relation=raw["relation"], weight=raw.get("weight", 1.0),
                created_at=raw.get("created_at", time.time()),
                metadata=dict(raw.get("metadata") or {}),
            )
            graph.edges[edge.id] = edge
            _persist_edge(session_id, edge)


def clear_graph(session_id: str) -> int:
    with _lock:
        graph = _graph_stores.get(session_id)
        count = 0
        if graph:
            count = len(graph.nodes) + len(graph.edges)
            _graph_stores.pop(session_id, None)
        conn = _conn()
        cur = conn.execute("SELECT COUNT(*) FROM nodes WHERE session_id = ?", (session_id,))
        n_count = cur.fetchone()[0]
        cur = conn.execute("SELECT COUNT(*) FROM edges WHERE session_id = ?", (session_id,))
        e_count = cur.fetchone()[0]
        if count == 0:
            count = n_count + e_count
        conn.execute("DELETE FROM nodes WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM edges WHERE session_id = ?", (session_id,))
        conn.commit()
        return count


def reload_session_from_db(session_id: str) -> Dict[str, int]:
    """Drop in-memory cache and reload from SQLite (simulates process restart)."""
    with _lock:
        _graph_stores.pop(session_id, None)
        graph = _get_graph(session_id)
        return {"nodes": len(graph.nodes), "edges": len(graph.edges)}
