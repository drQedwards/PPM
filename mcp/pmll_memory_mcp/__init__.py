"""
pmll_memory_mcp — PMLL Memory MCP Server package.

Provides a Model Context Protocol (MCP) server that exposes:
  - Short-term KV memory layer backed by PMLL (Persistent Memory Linked List)
    semantics and Q-promise async continuations
  - Long-term semantic memory graph (Context+ solution engine) with stable
    hashing embeddings, SQLite persistence, typed nodes/edges, and traversal
  - Solution engine for unified context resolution across both layers
"""

from .kv_store import PMMemoryStore
from .q_promise_bridge import QPromiseRegistry
from .peek import peek_context
from .embeddings import TfIdfVectorizer, HashingVectorizer, embed, cosine_similarity, EMBED_DIM
from .memory_graph import (
    upsert_node,
    create_relation,
    search_graph,
    prune_stale_links,
    add_interlinked_context,
    retrieve_with_traversal,
    get_graph_stats,
    clear_graph,
    configure_db,
    export_graph,
    import_graph,
    reload_session_from_db,
)
from .solution_engine import resolve_context, promote_to_long_term, get_memory_status

__all__ = [
    "PMMemoryStore",
    "QPromiseRegistry",
    "peek_context",
    "TfIdfVectorizer",
    "HashingVectorizer",
    "EMBED_DIM",
    "embed",
    "cosine_similarity",
    "upsert_node",
    "create_relation",
    "search_graph",
    "prune_stale_links",
    "add_interlinked_context",
    "retrieve_with_traversal",
    "get_graph_stats",
    "clear_graph",
    "configure_db",
    "export_graph",
    "import_graph",
    "reload_session_from_db",
    "resolve_context",
    "promote_to_long_term",
    "get_memory_status",
]
