"""
tests/test_memory_graph.py — Tests for long-term memory graph and embeddings.
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
# Embeddings
# ---------------------------------------------------------------------------


class TestTokenize:
    def test_basic_tokenization(self):
        tokens = tokenize("Hello World")
        assert tokens == ["hello", "world"]

    def test_removes_punctuation(self):
        tokens = tokenize("it's a test! right?")
        assert "test" in tokens
        assert "right" in tokens

    def test_filters_single_chars(self):
        tokens = tokenize("a b cd ef")
        assert "a" not in tokens
        assert "b" not in tokens
        assert "cd" in tokens


class TestTfIdfVectorizer:
    def test_empty_vectorizer(self):
        v = TfIdfVectorizer()
        assert v.vocab_size == 0
        assert v.vectorize("hello") == []

    def test_add_document_grows_vocab(self):
        v = TfIdfVectorizer()
        v.add_document("hello world")
        assert v.vocab_size == 2

    def test_vectorize_returns_correct_dimension(self):
        v = TfIdfVectorizer()
        v.add_document("hello world test")
        vec = v.vectorize("hello world test")
        assert len(vec) == 3

    def test_similar_texts_have_high_similarity(self):
        v = TfIdfVectorizer()
        v.add_document("authentication login user")
        v.add_document("authentication login password")
        vec1 = v.vectorize("authentication login user")
        vec2 = v.vectorize("authentication login password")
        sim = cosine_similarity(vec1, vec2)
        assert sim > 0.5


class TestCosineSimilarity:
    def test_identical_vectors(self):
        assert cosine_similarity([1, 0, 0], [1, 0, 0]) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        assert cosine_similarity([1, 0], [0, 1]) == pytest.approx(0.0)

    def test_empty_vectors(self):
        assert cosine_similarity([], []) == 0.0


# ---------------------------------------------------------------------------
# Memory Graph: upsert_node
# ---------------------------------------------------------------------------


class TestUpsertNode:
    def test_creates_new_node(self):
        node = upsert_node("s1", "concept", "auth", "authentication module")
        assert node.id.startswith("mn-")
        assert node.type == "concept"
        assert node.label == "auth"
        assert node.content == "authentication module"
        assert node.access_count == 1

    def test_updates_existing_node(self):
        n1 = upsert_node("s1", "concept", "auth", "v1")
        n2 = upsert_node("s1", "concept", "auth", "v2")
        assert n1.id == n2.id
        assert n2.content == "v2"
        assert n2.access_count == 2

    def test_different_types_separate_nodes(self):
        n1 = upsert_node("s1", "concept", "auth", "concept")
        n2 = upsert_node("s1", "file", "auth", "file")
        assert n1.id != n2.id

    def test_stores_metadata(self):
        node = upsert_node("s1", "note", "todo", "fix bug", {"priority": "high"})
        assert node.metadata["priority"] == "high"


# ---------------------------------------------------------------------------
# Memory Graph: create_relation
# ---------------------------------------------------------------------------


class TestCreateRelation:
    def test_creates_edge(self):
        n1 = upsert_node("s1", "concept", "a", "node a")
        n2 = upsert_node("s1", "concept", "b", "node b")
        edge = create_relation("s1", n1.id, n2.id, "depends_on")
        assert edge is not None
        assert edge.relation == "depends_on"
        assert edge.weight == 1.0

    def test_returns_none_for_missing_source(self):
        n2 = upsert_node("s1", "concept", "b", "b")
        assert create_relation("s1", "ghost", n2.id, "depends_on") is None

    def test_returns_none_for_missing_target(self):
        n1 = upsert_node("s1", "concept", "a", "a")
        assert create_relation("s1", n1.id, "ghost", "depends_on") is None

    def test_deduplicates(self):
        n1 = upsert_node("s1", "concept", "a", "a")
        n2 = upsert_node("s1", "concept", "b", "b")
        e1 = create_relation("s1", n1.id, n2.id, "depends_on", 0.5)
        e2 = create_relation("s1", n1.id, n2.id, "depends_on", 0.9)
        assert e1.id == e2.id
        assert e2.weight == 0.9


# ---------------------------------------------------------------------------
# Memory Graph: search_graph
# ---------------------------------------------------------------------------


class TestSearchGraph:
    def test_empty_graph_returns_empty(self):
        result = search_graph("empty", "test")
        assert result.direct == []
        assert result.total_nodes == 0

    def test_finds_direct_matches(self):
        upsert_node("s1", "concept", "authentication", "user auth login")
        upsert_node("s1", "concept", "database", "postgres connection pool")
        result = search_graph("s1", "authentication login")
        assert len(result.direct) > 0
        assert result.total_nodes == 2


# ---------------------------------------------------------------------------
# Memory Graph: prune_stale_links
# ---------------------------------------------------------------------------


class TestPruneStaleLinks:
    def test_noop_empty_graph(self):
        result = prune_stale_links("empty")
        assert result["removed"] == 0

    def test_does_not_remove_fresh_edges(self):
        n1 = upsert_node("s1", "concept", "a", "a")
        n2 = upsert_node("s1", "concept", "b", "b")
        create_relation("s1", n1.id, n2.id, "relates_to")
        result = prune_stale_links("s1")
        assert result["removed"] == 0
        assert result["remaining"] == 1


# ---------------------------------------------------------------------------
# Memory Graph: add_interlinked_context
# ---------------------------------------------------------------------------


class TestAddInterlinkedContext:
    def test_adds_multiple_nodes(self):
        result = add_interlinked_context("s1", [
            {"type": "concept", "label": "a", "content": "concept a"},
            {"type": "concept", "label": "b", "content": "concept b"},
            {"type": "concept", "label": "c", "content": "concept c"},
        ])
        assert len(result["nodes"]) == 3

    def test_no_edges_without_autolink(self):
        result = add_interlinked_context(
            "s1",
            [
                {"type": "concept", "label": "x", "content": "x content"},
                {"type": "concept", "label": "y", "content": "y content"},
            ],
            auto_link=False,
        )
        assert len(result["edges"]) == 0


# ---------------------------------------------------------------------------
# Memory Graph: retrieve_with_traversal
# ---------------------------------------------------------------------------


class TestRetrieveWithTraversal:
    def test_empty_for_unknown_node(self):
        results = retrieve_with_traversal("s1", "ghost")
        assert results == []

    def test_returns_start_and_neighbors(self):
        n1 = upsert_node("s1", "concept", "root", "root node")
        n2 = upsert_node("s1", "concept", "child", "child node")
        create_relation("s1", n1.id, n2.id, "contains")
        results = retrieve_with_traversal("s1", n1.id, max_depth=1)
        assert len(results) >= 2
        assert results[0].node.id == n1.id
        assert results[0].depth == 0
        assert results[0].relevance_score == 100.0


# ---------------------------------------------------------------------------
# Memory Graph: get_graph_stats, clear_graph
# ---------------------------------------------------------------------------


class TestGraphStats:
    def test_empty_graph_stats(self):
        stats = get_graph_stats("empty")
        assert stats["nodes"] == 0
        assert stats["edges"] == 0

    def test_correct_counts(self):
        n1 = upsert_node("s1", "concept", "a", "a")
        n2 = upsert_node("s1", "file", "b", "b")
        create_relation("s1", n1.id, n2.id, "references")
        stats = get_graph_stats("s1")
        assert stats["nodes"] == 2
        assert stats["edges"] == 1
        assert stats["types"]["concept"] == 1
        assert stats["types"]["file"] == 1
        assert stats["relations"]["references"] == 1


class TestClearGraph:
    def test_clear_empty_returns_zero(self):
        assert clear_graph("ghost") == 0

    def test_clears_nodes_and_edges(self):
        n1 = upsert_node("s1", "concept", "a", "a")
        n2 = upsert_node("s1", "concept", "b", "b")
        create_relation("s1", n1.id, n2.id, "relates_to")
        cleared = clear_graph("s1")
        assert cleared == 3  # 2 nodes + 1 edge
        stats = get_graph_stats("s1")
        assert stats["nodes"] == 0


# ---------------------------------------------------------------------------
# Session isolation
# ---------------------------------------------------------------------------


class TestGraphSessionIsolation:
    def test_independent_sessions(self):
        upsert_node("sA", "concept", "x", "session A")
        upsert_node("sB", "concept", "y", "session B")
        assert get_graph_stats("sA")["nodes"] == 1
        assert get_graph_stats("sB")["nodes"] == 1
