/**
 * contextplus-speed.test.ts — Speed benchmarks for Context+ MCP tools (standalone).
 *
 * Measures the performance of the 6 long-term memory graph tools adapted from
 * Context+ (github.com/ForLoopCodes/contextplus) WITHOUT any peek/KV cache layer.
 * These are the raw Context+ operations:
 *   - upsert_memory_node
 *   - create_relation
 *   - search_memory_graph
 *   - prune_stale_links
 *   - add_interlinked_context
 *   - retrieve_with_traversal
 *
 * Also benchmarks the TF-IDF embedding engine (tokenize, vectorize, cosine similarity).
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
import {
  tokenize,
  TfIdfVectorizer,
  cosineSimilarity,
  embed,
  resetVectorizer,
} from "../src/embeddings.js";

beforeEach(() => {
  _graphStoresMap.clear();
  resetVectorizer();
});

// ---------------------------------------------------------------------------
// Embedding engine benchmarks (no peek, no KV)
// ---------------------------------------------------------------------------

describe("Context+ Embeddings — standalone speed", () => {
  it("tokenize: 100 strings", () => {
    for (let i = 0; i < 100; i++) {
      tokenize(`authentication module for user login system version ${i}`);
    }
  });

  it("TfIdfVectorizer: build vocab from 50 documents", () => {
    const v = new TfIdfVectorizer();
    for (let i = 0; i < 50; i++) {
      v.addDocument(
        `document ${i} about authentication login session management caching memory`,
      );
    }
    expect(v.vocabSize).toBeGreaterThan(0);
  });

  it("TfIdfVectorizer: vectorize 50 queries against 50-doc corpus", () => {
    const v = new TfIdfVectorizer();
    for (let i = 0; i < 50; i++) {
      v.addDocument(
        `document ${i} covers topics like caching memory graph semantic search`,
      );
    }
    for (let i = 0; i < 50; i++) {
      const vec = v.vectorize(`query about caching and memory topic ${i}`);
      expect(vec.length).toBeGreaterThan(0);
    }
  });

  it("cosineSimilarity: 1000 vector comparisons", () => {
    const v = new TfIdfVectorizer();
    v.addDocument("authentication login session user");
    v.addDocument("database postgres connection pool query");
    const vecA = v.vectorize("authentication login");
    const vecB = v.vectorize("database connection");
    for (let i = 0; i < 1000; i++) {
      cosineSimilarity(vecA, vecB);
    }
  });

  it("embed: 100 documents through global vectorizer", () => {
    for (let i = 0; i < 100; i++) {
      const vec = embed(`concept ${i} about semantic graph traversal and memory nodes`);
      expect(vec.length).toBeGreaterThan(0);
    }
  });
});

// ---------------------------------------------------------------------------
// upsert_memory_node benchmarks (no peek, no KV)
// ---------------------------------------------------------------------------

describe("Context+ upsert_memory_node — standalone speed", () => {
  it("upsert 10 nodes (cold start)", () => {
    for (let i = 0; i < 10; i++) {
      const node = upsertNode("bench", "concept", `topic-${i}`, `content about topic ${i}`);
      expect(node.id).toMatch(/^mn-/);
    }
    const stats = getGraphStats("bench");
    expect(stats.nodes).toBe(10);
  });

  it("upsert 50 nodes", () => {
    for (let i = 0; i < 50; i++) {
      upsertNode("bench", "concept", `node-${i}`, `detailed content for node ${i} covering various topics`);
    }
    expect(getGraphStats("bench").nodes).toBe(50);
  });

  it("upsert 100 nodes", () => {
    for (let i = 0; i < 100; i++) {
      upsertNode("bench", "concept", `large-${i}`, `node ${i} with embedded content about graphs, memory, and semantics`);
    }
    expect(getGraphStats("bench").nodes).toBe(100);
  });

  it("update existing nodes (50 upserts on same labels)", () => {
    for (let i = 0; i < 50; i++) {
      upsertNode("bench", "concept", `shared-${i % 10}`, `version ${i} content`);
    }
    // 10 unique labels, each updated multiple times
    expect(getGraphStats("bench").nodes).toBe(10);
  });

  it("mixed node types (concept, file, symbol, note)", () => {
    const types = ["concept", "file", "symbol", "note"] as const;
    for (let i = 0; i < 40; i++) {
      upsertNode("bench", types[i % 4], `item-${i}`, `content for ${types[i % 4]} item ${i}`);
    }
    expect(getGraphStats("bench").nodes).toBe(40);
  });
});

// ---------------------------------------------------------------------------
// create_relation benchmarks (no peek, no KV)
// ---------------------------------------------------------------------------

describe("Context+ create_relation — standalone speed", () => {
  it("create 20 edges in a chain", () => {
    const nodes = [];
    for (let i = 0; i < 21; i++) {
      nodes.push(upsertNode("bench", "concept", `chain-${i}`, `chain node ${i}`));
    }
    for (let i = 0; i < 20; i++) {
      const edge = createRelation("bench", nodes[i].id, nodes[i + 1].id, "depends_on");
      expect(edge).not.toBeNull();
    }
    expect(getGraphStats("bench").edges).toBe(20);
  });

  it("create edges with all relation types", () => {
    const types = ["relates_to", "depends_on", "implements", "references", "similar_to", "contains"] as const;
    const n1 = upsertNode("bench", "concept", "src", "source node");
    for (let i = 0; i < types.length; i++) {
      const target = upsertNode("bench", "concept", `tgt-${i}`, `target ${i}`);
      const edge = createRelation("bench", n1.id, target.id, types[i]);
      expect(edge).not.toBeNull();
      expect(edge!.relation).toBe(types[i]);
    }
  });

  it("create 50 edges in a fully connected cluster of 10 nodes", () => {
    const nodes = [];
    for (let i = 0; i < 10; i++) {
      nodes.push(upsertNode("bench", "concept", `cluster-${i}`, `cluster node ${i}`));
    }
    let edgeCount = 0;
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        createRelation("bench", nodes[i].id, nodes[j].id, "relates_to", 0.8);
        edgeCount++;
      }
    }
    expect(edgeCount).toBe(45);
  });
});

// ---------------------------------------------------------------------------
// search_memory_graph benchmarks (no peek, no KV)
// ---------------------------------------------------------------------------

describe("Context+ search_memory_graph — standalone speed", () => {
  it("search empty graph", () => {
    const result = searchGraph("empty-bench", "any query");
    expect(result.direct).toHaveLength(0);
  });

  it("search across 10 nodes", () => {
    for (let i = 0; i < 10; i++) {
      upsertNode("bench", "concept", `topic-${i}`, `detailed content about topic number ${i} covering different areas`);
    }
    const result = searchGraph("bench", "topic content areas");
    expect(result.direct.length).toBeGreaterThan(0);
    expect(result.totalNodes).toBe(10);
  });

  it("search across 50 nodes", () => {
    for (let i = 0; i < 50; i++) {
      upsertNode("bench", "concept", `item-${i}`, `content about item ${i} with semantic graph features`);
    }
    const result = searchGraph("bench", "semantic graph features");
    expect(result.direct.length).toBeGreaterThan(0);
    expect(result.totalNodes).toBe(50);
  });

  it("search across 100 nodes with depth-2 traversal", () => {
    // Build 100 nodes with edge chain
    const nodes = [];
    for (let i = 0; i < 100; i++) {
      nodes.push(
        upsertNode("bench", "concept", `big-${i}`, `large scale node ${i} about memory and retrieval`),
      );
    }
    for (let i = 0; i < 99; i++) {
      createRelation("bench", nodes[i].id, nodes[i + 1].id, "relates_to");
    }
    const result = searchGraph("bench", "memory retrieval", 2, 10);
    expect(result.direct.length).toBeGreaterThan(0);
    expect(result.totalNodes).toBe(100);
    expect(result.totalEdges).toBe(99);
  });

  it("10 successive searches on same graph", () => {
    for (let i = 0; i < 20; i++) {
      upsertNode("bench", "concept", `doc-${i}`, `document about engineering practices ${i}`);
    }
    for (let q = 0; q < 10; q++) {
      const result = searchGraph("bench", `engineering practice query ${q}`);
      expect(result.direct.length).toBeGreaterThan(0);
    }
  });
});

// ---------------------------------------------------------------------------
// prune_stale_links benchmarks (no peek, no KV)
// ---------------------------------------------------------------------------

describe("Context+ prune_stale_links — standalone speed", () => {
  it("prune on graph with 50 fresh edges (no removals expected)", () => {
    const nodes = [];
    for (let i = 0; i < 51; i++) {
      nodes.push(upsertNode("bench", "concept", `prune-${i}`, `node ${i}`));
    }
    for (let i = 0; i < 50; i++) {
      createRelation("bench", nodes[i].id, nodes[i + 1].id, "depends_on");
    }
    const result = pruneStaleLinks("bench");
    expect(result.removed).toBe(0);
    expect(result.remaining).toBe(50);
  });

  it("prune on empty graph", () => {
    const result = pruneStaleLinks("empty-bench");
    expect(result.removed).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// add_interlinked_context benchmarks (no peek, no KV)
// ---------------------------------------------------------------------------

describe("Context+ add_interlinked_context — standalone speed", () => {
  it("bulk add 5 nodes with auto-linking", () => {
    const result = addInterlinkedContext("bench", [
      { type: "concept", label: "auth", content: "authentication and authorization module" },
      { type: "concept", label: "session", content: "session management and authentication tokens" },
      { type: "concept", label: "crypto", content: "cryptographic hashing for authentication" },
      { type: "concept", label: "oauth", content: "OAuth 2.0 authentication provider" },
      { type: "concept", label: "jwt", content: "JSON Web Token authentication" },
    ]);
    expect(result.nodes).toHaveLength(5);
    // auto-linking may create edges for similar nodes
  });

  it("bulk add 20 nodes with auto-linking", () => {
    const items = [];
    for (let i = 0; i < 20; i++) {
      items.push({
        type: "concept" as const,
        label: `batch-${i}`,
        content: `batch content about graph and memory operations number ${i}`,
      });
    }
    const result = addInterlinkedContext("bench", items);
    expect(result.nodes).toHaveLength(20);
  });

  it("bulk add 10 nodes without auto-linking", () => {
    const items = [];
    for (let i = 0; i < 10; i++) {
      items.push({
        type: "concept" as const,
        label: `nolink-${i}`,
        content: `content ${i}`,
      });
    }
    const result = addInterlinkedContext("bench", items, false);
    expect(result.nodes).toHaveLength(10);
    expect(result.edges).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// retrieve_with_traversal benchmarks (no peek, no KV)
// ---------------------------------------------------------------------------

describe("Context+ retrieve_with_traversal — standalone speed", () => {
  it("traverse depth-1 from root with 10 children", () => {
    const root = upsertNode("bench", "concept", "root", "root of the graph");
    for (let i = 0; i < 10; i++) {
      const child = upsertNode("bench", "concept", `child-${i}`, `child node ${i}`);
      createRelation("bench", root.id, child.id, "contains");
    }
    const results = retrieveWithTraversal("bench", root.id, 1);
    expect(results.length).toBe(11); // root + 10 children
    expect(results[0].node.id).toBe(root.id);
    expect(results[0].depth).toBe(0);
  });

  it("traverse depth-2 from root through 3-level tree", () => {
    const root = upsertNode("bench", "concept", "top", "top level");
    const mids = [];
    for (let i = 0; i < 5; i++) {
      const mid = upsertNode("bench", "concept", `mid-${i}`, `mid level ${i}`);
      createRelation("bench", root.id, mid.id, "contains");
      mids.push(mid);
    }
    for (const mid of mids) {
      for (let j = 0; j < 4; j++) {
        const leaf = upsertNode("bench", "concept", `leaf-${mid.label}-${j}`, `leaf under ${mid.label}`);
        createRelation("bench", mid.id, leaf.id, "contains");
      }
    }
    const results = retrieveWithTraversal("bench", root.id, 2);
    // root(1) + mids(5) + leaves(20) = 26
    expect(results.length).toBe(26);
  });

  it("traverse with edge filter", () => {
    const root = upsertNode("bench", "concept", "filtered-root", "root");
    const dep = upsertNode("bench", "concept", "dependency", "dep node");
    const ref = upsertNode("bench", "concept", "reference", "ref node");
    createRelation("bench", root.id, dep.id, "depends_on");
    createRelation("bench", root.id, ref.id, "references");
    const results = retrieveWithTraversal("bench", root.id, 1, ["depends_on"]);
    expect(results.length).toBe(2); // root + dep only
  });

  it("traverse depth-3 chain of 30 nodes", () => {
    const nodes = [];
    for (let i = 0; i < 30; i++) {
      nodes.push(upsertNode("bench", "concept", `chain-${i}`, `chain node ${i}`));
    }
    for (let i = 0; i < 29; i++) {
      createRelation("bench", nodes[i].id, nodes[i + 1].id, "relates_to");
    }
    const results = retrieveWithTraversal("bench", nodes[0].id, 3);
    // depth 0: node[0], depth 1: node[1], depth 2: node[2], depth 3: node[3]
    expect(results.length).toBe(4);
  });
});
