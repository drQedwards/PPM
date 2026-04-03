/**
 * memory-graph.test.ts — Tests for long-term memory graph and embeddings.
 */

import { describe, it, expect, beforeEach } from "vitest";
import {
  upsertNode,
  createRelation,
  searchGraph,
  pruneStaleLinks,
  addInterlinkedContext,
  retrieveWithTraversal,
  getGraphStats,
  clearGraph,
  _graphStoresMap,
} from "../src/memory-graph.js";
import { resetVectorizer } from "../src/embeddings.js";

beforeEach(() => {
  _graphStoresMap.clear();
  resetVectorizer();
});

// ---------------------------------------------------------------------------
// upsertNode
// ---------------------------------------------------------------------------

describe("upsertNode", () => {
  it("creates a new node", () => {
    const node = upsertNode("s1", "concept", "auth", "authentication module");
    expect(node.id).toMatch(/^mn-/);
    expect(node.type).toBe("concept");
    expect(node.label).toBe("auth");
    expect(node.content).toBe("authentication module");
    expect(node.accessCount).toBe(1);
    expect(node.embedding.length).toBeGreaterThan(0);
  });

  it("updates existing node with same label+type", () => {
    const n1 = upsertNode("s1", "concept", "auth", "v1");
    const n2 = upsertNode("s1", "concept", "auth", "v2");
    expect(n1.id).toBe(n2.id);
    expect(n2.content).toBe("v2");
    expect(n2.accessCount).toBe(2);
  });

  it("different types create separate nodes", () => {
    const n1 = upsertNode("s1", "concept", "auth", "concept");
    const n2 = upsertNode("s1", "file", "auth", "file");
    expect(n1.id).not.toBe(n2.id);
  });

  it("stores metadata", () => {
    const node = upsertNode("s1", "note", "todo", "fix bug", { priority: "high" });
    expect(node.metadata.priority).toBe("high");
  });
});

// ---------------------------------------------------------------------------
// createRelation
// ---------------------------------------------------------------------------

describe("createRelation", () => {
  it("creates edge between existing nodes", () => {
    const n1 = upsertNode("s1", "concept", "a", "node a");
    const n2 = upsertNode("s1", "concept", "b", "node b");
    const edge = createRelation("s1", n1.id, n2.id, "depends_on");
    expect(edge).not.toBeNull();
    expect(edge!.relation).toBe("depends_on");
    expect(edge!.weight).toBe(1.0);
  });

  it("returns null for missing source", () => {
    const n2 = upsertNode("s1", "concept", "b", "node b");
    const edge = createRelation("s1", "ghost", n2.id, "depends_on");
    expect(edge).toBeNull();
  });

  it("returns null for missing target", () => {
    const n1 = upsertNode("s1", "concept", "a", "node a");
    const edge = createRelation("s1", n1.id, "ghost", "depends_on");
    expect(edge).toBeNull();
  });

  it("deduplicates same source→target→relation", () => {
    const n1 = upsertNode("s1", "concept", "a", "node a");
    const n2 = upsertNode("s1", "concept", "b", "node b");
    const e1 = createRelation("s1", n1.id, n2.id, "depends_on", 0.5);
    const e2 = createRelation("s1", n1.id, n2.id, "depends_on", 0.9);
    expect(e1!.id).toBe(e2!.id);
    expect(e2!.weight).toBe(0.9);
  });
});

// ---------------------------------------------------------------------------
// searchGraph
// ---------------------------------------------------------------------------

describe("searchGraph", () => {
  it("returns empty for empty graph", () => {
    const result = searchGraph("empty", "test query");
    expect(result.direct).toHaveLength(0);
    expect(result.totalNodes).toBe(0);
  });

  it("finds direct matches", () => {
    upsertNode("s1", "concept", "authentication", "user auth module handles login");
    upsertNode("s1", "concept", "database", "postgres database connection pool");
    const result = searchGraph("s1", "authentication login");
    expect(result.direct.length).toBeGreaterThan(0);
    expect(result.totalNodes).toBe(2);
  });

  it("finds neighbors through edges", () => {
    const n1 = upsertNode("s1", "concept", "auth", "authentication module");
    const n2 = upsertNode("s1", "concept", "session", "session management");
    createRelation("s1", n1.id, n2.id, "depends_on");
    const result = searchGraph("s1", "auth", 1, 5);
    expect(result.direct.length).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// pruneStaleLinks
// ---------------------------------------------------------------------------

describe("pruneStaleLinks", () => {
  it("no-op on empty graph", () => {
    const result = pruneStaleLinks("empty");
    expect(result.removed).toBe(0);
    expect(result.remaining).toBe(0);
  });

  it("does not remove fresh edges", () => {
    const n1 = upsertNode("s1", "concept", "a", "a");
    const n2 = upsertNode("s1", "concept", "b", "b");
    createRelation("s1", n1.id, n2.id, "relates_to");
    const result = pruneStaleLinks("s1");
    expect(result.removed).toBe(0);
    expect(result.remaining).toBe(1);
  });
});

// ---------------------------------------------------------------------------
// addInterlinkedContext
// ---------------------------------------------------------------------------

describe("addInterlinkedContext", () => {
  it("adds multiple nodes", () => {
    const result = addInterlinkedContext("s1", [
      { type: "concept", label: "a", content: "concept a" },
      { type: "concept", label: "b", content: "concept b" },
      { type: "concept", label: "c", content: "concept c" },
    ]);
    expect(result.nodes).toHaveLength(3);
  });

  it("creates no edges with autoLink=false", () => {
    const result = addInterlinkedContext(
      "s1",
      [
        { type: "concept", label: "x", content: "x content" },
        { type: "concept", label: "y", content: "y content" },
      ],
      false,
    );
    expect(result.edges).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// retrieveWithTraversal
// ---------------------------------------------------------------------------

describe("retrieveWithTraversal", () => {
  it("returns empty for unknown node", () => {
    const results = retrieveWithTraversal("s1", "ghost");
    expect(results).toHaveLength(0);
  });

  it("returns starting node + neighbors", () => {
    const n1 = upsertNode("s1", "concept", "root", "root node");
    const n2 = upsertNode("s1", "concept", "child", "child node");
    createRelation("s1", n1.id, n2.id, "contains");
    const results = retrieveWithTraversal("s1", n1.id, 1);
    expect(results.length).toBeGreaterThanOrEqual(2);
    expect(results[0].node.id).toBe(n1.id);
    expect(results[0].depth).toBe(0);
    expect(results[0].relevanceScore).toBe(100);
  });
});

// ---------------------------------------------------------------------------
// getGraphStats
// ---------------------------------------------------------------------------

describe("getGraphStats", () => {
  it("returns zero counts for empty graph", () => {
    const stats = getGraphStats("empty");
    expect(stats.nodes).toBe(0);
    expect(stats.edges).toBe(0);
  });

  it("counts nodes and edges correctly", () => {
    const n1 = upsertNode("s1", "concept", "a", "a");
    const n2 = upsertNode("s1", "file", "b", "b");
    createRelation("s1", n1.id, n2.id, "references");
    const stats = getGraphStats("s1");
    expect(stats.nodes).toBe(2);
    expect(stats.edges).toBe(1);
    expect(stats.types.concept).toBe(1);
    expect(stats.types.file).toBe(1);
    expect(stats.relations.references).toBe(1);
  });
});

// ---------------------------------------------------------------------------
// clearGraph
// ---------------------------------------------------------------------------

describe("clearGraph", () => {
  it("returns 0 for empty graph", () => {
    expect(clearGraph("ghost")).toBe(0);
  });

  it("clears nodes and edges", () => {
    const n1 = upsertNode("s1", "concept", "a", "a");
    const n2 = upsertNode("s1", "concept", "b", "b");
    createRelation("s1", n1.id, n2.id, "relates_to");
    const cleared = clearGraph("s1");
    expect(cleared).toBe(3); // 2 nodes + 1 edge
    const stats = getGraphStats("s1");
    expect(stats.nodes).toBe(0);
    expect(stats.edges).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// Session isolation
// ---------------------------------------------------------------------------

describe("graph session isolation", () => {
  it("different sessions have independent graphs", () => {
    upsertNode("sA", "concept", "x", "session A node");
    upsertNode("sB", "concept", "y", "session B node");
    const statsA = getGraphStats("sA");
    const statsB = getGraphStats("sB");
    expect(statsA.nodes).toBe(1);
    expect(statsB.nodes).toBe(1);
  });
});
