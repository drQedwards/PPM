"""
tests/test_combined_speed.py — Speed benchmarks for Context+ AND PMLL/peek combined.

This is the fourth benchmark configuration: it exercises the full pipeline
where Context+ graph operations (upsert, search, traverse, interlink) feed
results into the PMLL peek/KV cache so that repeated lookups are served
from the cache at O(1) cost instead of re-executing graph operations.

The pattern tested:
    1. Build a graph (Context+ upsert_memory_node / create_relation)
    2. First search -> graph hit (expensive-ish: TF-IDF + traversal)
    3. Cache result in KV via set()
    4. Second search -> peek() cache hit (0ms, no graph work)

This should be the fastest per-test configuration because the majority of
operations are served from the KV cache after the initial graph population.
"""

import sys
import os

import pytest

MCP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, MCP_DIR)

from pmll_memory_mcp.embeddings import reset_vectorizer
from pmll_memory_mcp.memory_graph import (
    upsert_node,
    create_relation,
    search_graph,
    add_interlinked_context,
    retrieve_with_traversal,
    get_graph_stats,
    _graph_stores,
)
from pmll_memory_mcp.kv_store import PMMemoryStore, get_store, _session_stores
from pmll_memory_mcp.q_promise_bridge import QPromiseRegistry
from pmll_memory_mcp.peek import peek_context
from pmll_memory_mcp.solution_engine import (
    resolve_context,
    promote_to_long_term,
    get_memory_status,
)


@pytest.fixture(autouse=True)
def reset_state():
    """Reset all module-level state before each test."""
    _graph_stores.clear()
    _session_stores.clear()
    reset_vectorizer()
    yield
    _graph_stores.clear()
    _session_stores.clear()
    reset_vectorizer()


# ---------------------------------------------------------------------------
# Pattern 1: Graph build -> search -> cache -> peek hit
# ---------------------------------------------------------------------------


class TestGraphSearchCachedViaPeek:
    def test_search_10_node_graph_cache_and_peek(self):
        store = PMMemoryStore()
        registry = QPromiseRegistry()
        # Build graph
        for i in range(10):
            upsert_node("bench", "concept", f"topic-{i}", f"content about topic {i} covering authentication")
        # First search — hits the graph
        result = search_graph("bench", "authentication topic")
        assert len(result.direct) > 0
        # Cache the top result
        top_content = result.direct[0].node.content
        store.set("auth-search", top_content)
        # Repeated lookups — served from KV cache (0ms)
        for _ in range(20):
            peek = peek_context("auth-search", "bench", store, registry)
            assert peek["hit"] is True
            assert peek["value"] == top_content

    def test_search_50_node_graph_cache_top5_peek_all(self):
        store = PMMemoryStore()
        registry = QPromiseRegistry()
        for i in range(50):
            upsert_node("bench", "concept", f"item-{i}", f"content about item {i} with semantic graph features")
        result = search_graph("bench", "semantic graph features", top_k=5)
        assert len(result.direct) > 0
        # Cache top 5 results
        cached_count = min(5, len(result.direct))
        for j in range(cached_count):
            store.set(f"search-result-{j}", result.direct[j].node.content)
        # Peek all cached — instant
        for j in range(cached_count):
            peek = peek_context(f"search-result-{j}", "bench", store, registry)
            assert peek["hit"] is True

    def test_search_100_node_graph_depth2_cache_and_peek_50(self):
        store = PMMemoryStore()
        registry = QPromiseRegistry()
        nodes = []
        for i in range(100):
            nodes.append(
                upsert_node("bench", "concept", f"big-{i}", f"large scale node {i} about memory and retrieval")
            )
        for i in range(99):
            create_relation("bench", nodes[i].id, nodes[i + 1].id, "relates_to")
        result = search_graph("bench", "memory retrieval", max_depth=2, top_k=10)
        assert len(result.direct) > 0
        # Cache top result
        store.set("big-search", result.direct[0].node.content)
        # 50 repeated peeks — all cache hits (0ms each)
        for _ in range(50):
            peek = peek_context("big-search", "bench", store, registry)
            assert peek["hit"] is True


# ---------------------------------------------------------------------------
# Pattern 2: Interlinked context build -> cache -> peek
# ---------------------------------------------------------------------------


class TestInterlinkedContextCachedViaPeek:
    def test_bulk_add_20_nodes_cache_ids_peek_all(self):
        store = PMMemoryStore()
        registry = QPromiseRegistry()
        items = [
            {"type": "concept", "label": f"batch-{i}", "content": f"batch content about graph and memory operations number {i}"}
            for i in range(20)
        ]
        result = add_interlinked_context("bench", items)
        assert len(result["nodes"]) == 20
        # Cache all node IDs in KV
        for node in result["nodes"]:
            store.set(f"node:{node.label}", node.id)
        # Peek all 20 — instant cache hits
        for node in result["nodes"]:
            peek = peek_context(f"node:{node.label}", "bench", store, registry)
            assert peek["hit"] is True
            assert peek["value"] == node.id

    def test_bulk_add_5_related_search_cache_peek_10(self):
        store = PMMemoryStore()
        registry = QPromiseRegistry()
        add_interlinked_context("bench", [
            {"type": "concept", "label": "auth", "content": "authentication and authorization module"},
            {"type": "concept", "label": "session", "content": "session management and authentication tokens"},
            {"type": "concept", "label": "crypto", "content": "cryptographic hashing for authentication"},
            {"type": "concept", "label": "oauth", "content": "OAuth 2.0 authentication provider"},
            {"type": "concept", "label": "jwt", "content": "JSON Web Token authentication"},
        ])
        result = search_graph("bench", "authentication")
        assert len(result.direct) > 0
        store.set("auth-result", result.direct[0].node.content)
        for _ in range(10):
            peek = peek_context("auth-result", "bench", store, registry)
            assert peek["hit"] is True


# ---------------------------------------------------------------------------
# Pattern 3: Traversal -> cache -> peek
# ---------------------------------------------------------------------------


class TestTraversalCachedViaPeek:
    def test_traverse_3_level_tree_cache_peek_20(self):
        store = PMMemoryStore()
        registry = QPromiseRegistry()
        root = upsert_node("bench", "concept", "top", "top level")
        for i in range(5):
            mid = upsert_node("bench", "concept", f"mid-{i}", f"mid level {i}")
            create_relation("bench", root.id, mid.id, "contains")
            for j in range(4):
                leaf = upsert_node("bench", "concept", f"leaf-{i}-{j}", f"leaf under mid-{i}")
                create_relation("bench", mid.id, leaf.id, "contains")
        results = retrieve_with_traversal("bench", root.id, max_depth=2)
        assert len(results) == 26
        # Cache traversal result count + root info
        store.set("tree-size", str(len(results)))
        store.set("tree-root", root.id)
        # 20 repeated peeks — all instant
        for _ in range(20):
            peek1 = peek_context("tree-size", "bench", store, registry)
            assert peek1["hit"] is True
            peek2 = peek_context("tree-root", "bench", store, registry)
            assert peek2["hit"] is True

    def test_traverse_depth3_chain_cache_path_peek_30(self):
        store = PMMemoryStore()
        registry = QPromiseRegistry()
        nodes = []
        for i in range(30):
            nodes.append(upsert_node("bench", "concept", f"chain-{i}", f"chain node {i}"))
        for i in range(29):
            create_relation("bench", nodes[i].id, nodes[i + 1].id, "relates_to")
        results = retrieve_with_traversal("bench", nodes[0].id, max_depth=3)
        assert len(results) == 4
        # Cache path IDs
        path_ids = ",".join(r.node.id for r in results)
        store.set("chain-path", path_ids)
        # 30 repeated peeks
        for _ in range(30):
            peek = peek_context("chain-path", "bench", store, registry)
            assert peek["hit"] is True
            assert peek["value"] == path_ids


# ---------------------------------------------------------------------------
# Pattern 4: Solution engine — resolveContext with both layers active
# ---------------------------------------------------------------------------


class TestSolutionEngineBothLayers:
    def test_resolve_short_term_hit_after_caching_graph(self):
        store = get_store("s1")
        # Populate graph
        upsert_node("s1", "concept", "authentication", "user login system with OAuth")
        # First resolve — hits long-term graph
        first = resolve_context("s1", "authentication", store)
        assert first["source"] == "long_term"
        # Cache it in short-term
        store.set("authentication", first["value"])
        # Second resolve — hits short-term cache (faster)
        second = resolve_context("s1", "authentication", store)
        assert second["source"] == "short_term"
        assert second["score"] == 1.0

    def test_resolve_20_repeated_lookups_after_caching(self):
        store = get_store("s1")
        upsert_node("s1", "concept", "database", "PostgreSQL connection pooling configuration")
        first = resolve_context("s1", "database", store)
        assert first["source"] == "long_term"
        store.set("database", first["value"])
        for _ in range(20):
            cached = resolve_context("s1", "database", store)
            assert cached["source"] == "short_term"
            assert cached["score"] == 1.0

    def test_promote_then_resolve_both_layers(self):
        store = get_store("s1")
        # Start with a short-term entry
        store.set("config", "app-settings-v2")
        # Promote to long-term
        promoted = promote_to_long_term("s1", "config", "app-settings-v2", "note")
        assert promoted["promoted"] is True
        # resolveContext should find short-term first
        result = resolve_context("s1", "config", store)
        assert result["source"] == "short_term"
        assert result["value"] == "app-settings-v2"
        # After flushing short-term, should fall through to long-term
        store.flush()
        fallback = resolve_context("s1", "config", store)
        assert fallback["source"] == "long_term"

    def test_memory_status_reflects_both_layers(self):
        store = get_store("s1")
        store.set("k1", "v1")
        store.set("k2", "v2")
        store.set("k3", "v3")
        upsert_node("s1", "concept", "c1", "content 1")
        upsert_node("s1", "concept", "c2", "content 2")
        r1 = search_graph("s1", "c1", top_k=1)
        r2 = search_graph("s1", "c2", top_k=1)
        if r1.direct and r2.direct:
            create_relation("s1", r1.direct[0].node.id, r2.direct[0].node.id, "relates_to")
        status = get_memory_status("s1", store)
        assert status["short_term"]["slots"] == 3
        assert status["long_term"]["nodes"] == 2


# ---------------------------------------------------------------------------
# Pattern 5: Mixed workload — interleaved graph + cache operations
# ---------------------------------------------------------------------------


class TestMixedGraphCacheWorkload:
    def test_alternating_upsert_search_cache_peek_10_iterations(self):
        store = PMMemoryStore()
        registry = QPromiseRegistry()
        for i in range(10):
            # Upsert a new node
            upsert_node("bench", "concept", f"topic-{i}", f"content about topic {i} in the knowledge graph")
            # Search for it
            result = search_graph("bench", f"topic {i}")
            assert len(result.direct) > 0
            # Cache the search result
            store.set(f"topic-{i}", result.direct[0].node.content)
            # Peek — instant hit
            peek = peek_context(f"topic-{i}", "bench", store, registry)
            assert peek["hit"] is True
        assert len(store) == 10
        assert get_graph_stats("bench")["nodes"] == 10

    def test_build_50_cache_peek_flush_rebuild(self):
        store = PMMemoryStore()
        registry = QPromiseRegistry()
        # Phase 1: Build graph and cache
        for i in range(50):
            node = upsert_node("bench", "concept", f"item-{i}", f"item {i} data")
            store.set(f"item-{i}", node.id)
        # Phase 2: Peek all 50 from cache
        for i in range(50):
            peek = peek_context(f"item-{i}", "bench", store, registry)
            assert peek["hit"] is True
        # Phase 3: Flush cache
        cleared = store.flush()
        assert cleared == 50
        # Phase 4: All peeks are misses now
        for i in range(50):
            peek = peek_context(f"item-{i}", "bench", store, registry)
            assert peek["hit"] is False
        # Phase 5: Rebuild cache from graph search
        for i in range(50):
            result = search_graph("bench", f"item {i}")
            if result.direct:
                store.set(f"item-{i}", result.direct[0].node.content)
        # Phase 6: All peeks hit again
        for i in range(50):
            peek = peek_context(f"item-{i}", "bench", store, registry)
            assert peek["hit"] is True

    def test_10_successive_resolve_on_dual_layer(self):
        store = get_store("s1")
        # Populate both layers
        for i in range(10):
            upsert_node("s1", "concept", f"key-{i}", f"value for key {i}")
            store.set(f"key-{i}", f"cached-value-{i}")
        # All 10 resolve from short-term (fastest path)
        for i in range(10):
            result = resolve_context("s1", f"key-{i}", store)
            assert result["source"] == "short_term"
            assert result["score"] == 1.0
