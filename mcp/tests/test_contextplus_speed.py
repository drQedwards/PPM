"""
tests/test_contextplus_speed.py — Speed benchmarks for Context+ MCP tools (standalone).

Measures the performance of the 6 long-term memory graph tools adapted from
Context+ (github.com/ForLoopCodes/contextplus) WITHOUT any peek/KV cache layer.
Also benchmarks the TF-IDF embedding engine.
"""

import sys
import os

import pytest

MCP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, MCP_DIR)

from pmll_memory_mcp.embeddings import (
    tokenize,
    TfIdfVectorizer,
    cosine_similarity,
    embed,
    reset_vectorizer,
)
from pmll_memory_mcp.memory_graph import (
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


@pytest.fixture(autouse=True)
def reset_state():
    """Reset all module-level state before each test."""
    _graph_stores.clear()
    reset_vectorizer()
    yield
    _graph_stores.clear()
    reset_vectorizer()


# ---------------------------------------------------------------------------
# Embedding engine benchmarks (no peek, no KV)
# ---------------------------------------------------------------------------


class TestEmbeddingsStandaloneSpeed:
    def test_tokenize_100_strings(self):
        for i in range(100):
            tokenize(f"authentication module for user login system version {i}")

    def test_tfidf_build_vocab_from_50_documents(self):
        v = TfIdfVectorizer()
        for i in range(50):
            v.add_document(
                f"document {i} about authentication login session management caching memory"
            )
        assert v.vocab_size > 0

    def test_tfidf_vectorize_50_queries_against_50_doc_corpus(self):
        v = TfIdfVectorizer()
        for i in range(50):
            v.add_document(
                f"document {i} covers topics like caching memory graph semantic search"
            )
        for i in range(50):
            vec = v.vectorize(f"query about caching and memory topic {i}")
            assert len(vec) > 0

    def test_cosine_similarity_1000_comparisons(self):
        v = TfIdfVectorizer()
        v.add_document("authentication login session user")
        v.add_document("database postgres connection pool query")
        vec_a = v.vectorize("authentication login")
        vec_b = v.vectorize("database connection")
        for _ in range(1000):
            cosine_similarity(vec_a, vec_b)

    def test_embed_100_documents(self):
        for i in range(100):
            vec = embed(f"concept {i} about semantic graph traversal and memory nodes")
            assert len(vec) > 0


# ---------------------------------------------------------------------------
# upsert_memory_node benchmarks (no peek, no KV)
# ---------------------------------------------------------------------------


class TestUpsertNodeStandaloneSpeed:
    def test_upsert_10_nodes_cold_start(self):
        for i in range(10):
            node = upsert_node("bench", "concept", f"topic-{i}", f"content about topic {i}")
            assert node.id.startswith("mn-")
        stats = get_graph_stats("bench")
        assert stats["nodes"] == 10

    def test_upsert_50_nodes(self):
        for i in range(50):
            upsert_node(
                "bench", "concept", f"node-{i}",
                f"detailed content for node {i} covering various topics",
            )
        assert get_graph_stats("bench")["nodes"] == 50

    def test_upsert_100_nodes(self):
        for i in range(100):
            upsert_node(
                "bench", "concept", f"large-{i}",
                f"node {i} with embedded content about graphs, memory, and semantics",
            )
        assert get_graph_stats("bench")["nodes"] == 100

    def test_update_existing_nodes_50_upserts(self):
        for i in range(50):
            upsert_node("bench", "concept", f"shared-{i % 10}", f"version {i} content")
        assert get_graph_stats("bench")["nodes"] == 10

    def test_mixed_node_types(self):
        types = ["concept", "file", "symbol", "note"]
        for i in range(40):
            upsert_node(
                "bench", types[i % 4], f"item-{i}",
                f"content for {types[i % 4]} item {i}",
            )
        assert get_graph_stats("bench")["nodes"] == 40


# ---------------------------------------------------------------------------
# create_relation benchmarks (no peek, no KV)
# ---------------------------------------------------------------------------


class TestCreateRelationStandaloneSpeed:
    def test_create_20_edges_in_chain(self):
        nodes = []
        for i in range(21):
            nodes.append(upsert_node("bench", "concept", f"chain-{i}", f"chain node {i}"))
        for i in range(20):
            edge = create_relation("bench", nodes[i].id, nodes[i + 1].id, "depends_on")
            assert edge is not None
        assert get_graph_stats("bench")["edges"] == 20

    def test_create_edges_with_all_relation_types(self):
        types = ["relates_to", "depends_on", "implements", "references", "similar_to", "contains"]
        n1 = upsert_node("bench", "concept", "src", "source node")
        for i, rt in enumerate(types):
            target = upsert_node("bench", "concept", f"tgt-{i}", f"target {i}")
            edge = create_relation("bench", n1.id, target.id, rt)
            assert edge is not None
            assert edge.relation == rt

    def test_create_45_edges_fully_connected_10_nodes(self):
        nodes = []
        for i in range(10):
            nodes.append(upsert_node("bench", "concept", f"cluster-{i}", f"cluster node {i}"))
        edge_count = 0
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                create_relation("bench", nodes[i].id, nodes[j].id, "relates_to", 0.8)
                edge_count += 1
        assert edge_count == 45


# ---------------------------------------------------------------------------
# search_memory_graph benchmarks (no peek, no KV)
# ---------------------------------------------------------------------------


class TestSearchGraphStandaloneSpeed:
    def test_search_empty_graph(self):
        result = search_graph("empty-bench", "any query")
        assert result.direct == []

    def test_search_across_10_nodes(self):
        for i in range(10):
            upsert_node(
                "bench", "concept", f"topic-{i}",
                f"detailed content about topic number {i} covering different areas",
            )
        result = search_graph("bench", "topic content areas")
        assert len(result.direct) > 0
        assert result.total_nodes == 10

    def test_search_across_50_nodes(self):
        for i in range(50):
            upsert_node(
                "bench", "concept", f"item-{i}",
                f"content about item {i} with semantic graph features",
            )
        result = search_graph("bench", "semantic graph features")
        assert len(result.direct) > 0
        assert result.total_nodes == 50

    def test_search_across_100_nodes_depth_2_traversal(self):
        nodes = []
        for i in range(100):
            nodes.append(
                upsert_node(
                    "bench", "concept", f"big-{i}",
                    f"large scale node {i} about memory and retrieval",
                )
            )
        for i in range(99):
            create_relation("bench", nodes[i].id, nodes[i + 1].id, "relates_to")
        result = search_graph("bench", "memory retrieval", max_depth=2, top_k=10)
        assert len(result.direct) > 0
        assert result.total_nodes == 100
        assert result.total_edges == 99

    def test_10_successive_searches(self):
        for i in range(20):
            upsert_node(
                "bench", "concept", f"doc-{i}",
                f"document about engineering practices {i}",
            )
        for q in range(10):
            result = search_graph("bench", f"engineering practice query {q}")
            assert len(result.direct) > 0


# ---------------------------------------------------------------------------
# prune_stale_links benchmarks (no peek, no KV)
# ---------------------------------------------------------------------------


class TestPruneStaleLinksStandaloneSpeed:
    def test_prune_50_fresh_edges(self):
        nodes = []
        for i in range(51):
            nodes.append(upsert_node("bench", "concept", f"prune-{i}", f"node {i}"))
        for i in range(50):
            create_relation("bench", nodes[i].id, nodes[i + 1].id, "depends_on")
        result = prune_stale_links("bench")
        assert result["removed"] == 0
        assert result["remaining"] == 50

    def test_prune_empty_graph(self):
        result = prune_stale_links("empty-bench")
        assert result["removed"] == 0


# ---------------------------------------------------------------------------
# add_interlinked_context benchmarks (no peek, no KV)
# ---------------------------------------------------------------------------


class TestAddInterlinkedContextStandaloneSpeed:
    def test_bulk_add_5_nodes_with_auto_linking(self):
        result = add_interlinked_context("bench", [
            {"type": "concept", "label": "auth", "content": "authentication and authorization module"},
            {"type": "concept", "label": "session", "content": "session management and authentication tokens"},
            {"type": "concept", "label": "crypto", "content": "cryptographic hashing for authentication"},
            {"type": "concept", "label": "oauth", "content": "OAuth 2.0 authentication provider"},
            {"type": "concept", "label": "jwt", "content": "JSON Web Token authentication"},
        ])
        assert len(result["nodes"]) == 5

    def test_bulk_add_20_nodes_with_auto_linking(self):
        items = [
            {"type": "concept", "label": f"batch-{i}", "content": f"batch content about graph and memory operations number {i}"}
            for i in range(20)
        ]
        result = add_interlinked_context("bench", items)
        assert len(result["nodes"]) == 20

    def test_bulk_add_10_nodes_without_auto_linking(self):
        items = [
            {"type": "concept", "label": f"nolink-{i}", "content": f"content {i}"}
            for i in range(10)
        ]
        result = add_interlinked_context("bench", items, auto_link=False)
        assert len(result["nodes"]) == 10
        assert len(result["edges"]) == 0


# ---------------------------------------------------------------------------
# retrieve_with_traversal benchmarks (no peek, no KV)
# ---------------------------------------------------------------------------


class TestRetrieveWithTraversalStandaloneSpeed:
    def test_traverse_depth_1_root_with_10_children(self):
        root = upsert_node("bench", "concept", "root", "root of the graph")
        for i in range(10):
            child = upsert_node("bench", "concept", f"child-{i}", f"child node {i}")
            create_relation("bench", root.id, child.id, "contains")
        results = retrieve_with_traversal("bench", root.id, max_depth=1)
        assert len(results) == 11  # root + 10 children
        assert results[0].node.id == root.id
        assert results[0].depth == 0

    def test_traverse_depth_2_through_3_level_tree(self):
        root = upsert_node("bench", "concept", "top", "top level")
        mids = []
        for i in range(5):
            mid = upsert_node("bench", "concept", f"mid-{i}", f"mid level {i}")
            create_relation("bench", root.id, mid.id, "contains")
            mids.append(mid)
        for mid in mids:
            for j in range(4):
                leaf = upsert_node("bench", "concept", f"leaf-{mid.label}-{j}", f"leaf under {mid.label}")
                create_relation("bench", mid.id, leaf.id, "contains")
        results = retrieve_with_traversal("bench", root.id, max_depth=2)
        assert len(results) == 26  # 1 root + 5 mids + 20 leaves

    def test_traverse_with_edge_filter(self):
        root = upsert_node("bench", "concept", "filtered-root", "root")
        dep = upsert_node("bench", "concept", "dependency", "dep node")
        ref = upsert_node("bench", "concept", "reference", "ref node")
        create_relation("bench", root.id, dep.id, "depends_on")
        create_relation("bench", root.id, ref.id, "references")
        results = retrieve_with_traversal("bench", root.id, max_depth=1, edge_filter=["depends_on"])
        assert len(results) == 2  # root + dep only

    def test_traverse_depth_3_chain_30_nodes(self):
        nodes = []
        for i in range(30):
            nodes.append(upsert_node("bench", "concept", f"chain-{i}", f"chain node {i}"))
        for i in range(29):
            create_relation("bench", nodes[i].id, nodes[i + 1].id, "relates_to")
        results = retrieve_with_traversal("bench", nodes[0].id, max_depth=3)
        assert len(results) == 4  # depth 0,1,2,3
