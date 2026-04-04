/**
 * combined-speed.test.ts — Speed benchmarks for Context+ AND PMLL/peek combined.
 *
 * This is the fourth benchmark configuration: it exercises the full pipeline
 * where Context+ graph operations (upsert, search, traverse, interlink) feed
 * results into the PMLL peek/KV cache so that repeated lookups are served
 * from the cache at O(1) cost instead of re-executing graph operations.
 *
 * The pattern tested:
 *   1. Build a graph (Context+ upsert_memory_node / create_relation)
 *   2. First search → graph hit (expensive-ish: TF-IDF + traversal)
 *   3. Cache result in KV via set()
 *   4. Second search → peek() cache hit (0ms, no graph work)
 *
 * This should be the fastest per-test configuration because the majority of
 * operations are served from the KV cache after the initial graph population.
 */

import { describe, it, expect, beforeEach } from "vitest";
import {
  upsertNode,
  createRelation,
  searchGraph,
  addInterlinkedContext,
  retrieveWithTraversal,
  getGraphStats,
  _graphStoresMap,
} from "../src/memory-graph.js";
import { resetVectorizer } from "../src/embeddings.js";
import { PMMemoryStore, getStore, _sessionStoresMap } from "../src/kv-store.js";
import { QPromiseRegistry } from "../src/q-promise-bridge.js";
import { peekContext } from "../src/peek.js";
import { resolveContext, promoteToLongTerm, getMemoryStatus } from "../src/solution-engine.js";

beforeEach(() => {
  _graphStoresMap.clear();
  _sessionStoresMap.clear();
  resetVectorizer();
});

// ---------------------------------------------------------------------------
// Pattern 1: Graph build → search → cache → peek hit
// ---------------------------------------------------------------------------

describe("Combined: graph search cached via peek", () => {
  it("search 10-node graph, cache result, peek hit on repeat", () => {
    const store = new PMMemoryStore();
    const registry = new QPromiseRegistry();
    // Build graph
    for (let i = 0; i < 10; i++) {
      upsertNode("bench", "concept", `topic-${i}`, `content about topic ${i} covering authentication`);
    }
    // First search — hits the graph
    const result = searchGraph("bench", "authentication topic");
    expect(result.direct.length).toBeGreaterThan(0);
    // Cache the top result
    const topContent = result.direct[0].node.content;
    store.set("auth-search", topContent);
    // Repeated lookups — served from KV cache (0ms)
    for (let i = 0; i < 20; i++) {
      const peek = peekContext("auth-search", "bench", store, registry);
      expect(peek.hit).toBe(true);
      if (peek.hit && "value" in peek) {
        expect(peek.value).toBe(topContent);
      }
    }
  });

  it("search 50-node graph, cache top-5 results, peek all 5", () => {
    const store = new PMMemoryStore();
    const registry = new QPromiseRegistry();
    for (let i = 0; i < 50; i++) {
      upsertNode("bench", "concept", `item-${i}`, `content about item ${i} with semantic graph features`);
    }
    const result = searchGraph("bench", "semantic graph features", 1, 5);
    expect(result.direct.length).toBeGreaterThan(0);
    // Cache top 5 results
    for (let j = 0; j < Math.min(5, result.direct.length); j++) {
      store.set(`search-result-${j}`, result.direct[j].node.content);
    }
    // Peek all cached — instant
    for (let j = 0; j < Math.min(5, result.direct.length); j++) {
      const peek = peekContext(`search-result-${j}`, "bench", store, registry);
      expect(peek.hit).toBe(true);
    }
  });

  it("search 100-node graph with depth-2, cache and peek 50 times", () => {
    const store = new PMMemoryStore();
    const registry = new QPromiseRegistry();
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
    // Cache top result
    store.set("big-search", result.direct[0].node.content);
    // 50 repeated peeks — all cache hits (0ms each)
    for (let i = 0; i < 50; i++) {
      const peek = peekContext("big-search", "bench", store, registry);
      expect(peek.hit).toBe(true);
    }
  });
});

// ---------------------------------------------------------------------------
// Pattern 2: Interlinked context build → cache → peek
// ---------------------------------------------------------------------------

describe("Combined: interlinked context cached via peek", () => {
  it("bulk add 20 nodes, cache node IDs, peek all", () => {
    const store = new PMMemoryStore();
    const registry = new QPromiseRegistry();
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
    // Cache all node IDs in KV
    for (const node of result.nodes) {
      store.set(`node:${node.label}`, node.id);
    }
    // Peek all 20 — instant cache hits
    for (const node of result.nodes) {
      const peek = peekContext(`node:${node.label}`, "bench", store, registry);
      expect(peek.hit).toBe(true);
      if (peek.hit && "value" in peek) {
        expect(peek.value).toBe(node.id);
      }
    }
  });

  it("bulk add 5 related nodes, search, cache, peek 10 times", () => {
    const store = new PMMemoryStore();
    const registry = new QPromiseRegistry();
    addInterlinkedContext("bench", [
      { type: "concept", label: "auth", content: "authentication and authorization module" },
      { type: "concept", label: "session", content: "session management and authentication tokens" },
      { type: "concept", label: "crypto", content: "cryptographic hashing for authentication" },
      { type: "concept", label: "oauth", content: "OAuth 2.0 authentication provider" },
      { type: "concept", label: "jwt", content: "JSON Web Token authentication" },
    ]);
    const result = searchGraph("bench", "authentication");
    expect(result.direct.length).toBeGreaterThan(0);
    store.set("auth-result", result.direct[0].node.content);
    for (let i = 0; i < 10; i++) {
      const peek = peekContext("auth-result", "bench", store, registry);
      expect(peek.hit).toBe(true);
    }
  });
});

// ---------------------------------------------------------------------------
// Pattern 3: Traversal → cache → peek
// ---------------------------------------------------------------------------

describe("Combined: traversal results cached via peek", () => {
  it("traverse 3-level tree, cache leaf count, peek 20 times", () => {
    const store = new PMMemoryStore();
    const registry = new QPromiseRegistry();
    const root = upsertNode("bench", "concept", "top", "top level");
    for (let i = 0; i < 5; i++) {
      const mid = upsertNode("bench", "concept", `mid-${i}`, `mid level ${i}`);
      createRelation("bench", root.id, mid.id, "contains");
      for (let j = 0; j < 4; j++) {
        const leaf = upsertNode("bench", "concept", `leaf-${i}-${j}`, `leaf under mid-${i}`);
        createRelation("bench", mid.id, leaf.id, "contains");
      }
    }
    const results = retrieveWithTraversal("bench", root.id, 2);
    expect(results.length).toBe(26);
    // Cache traversal result count + root info
    store.set("tree-size", String(results.length));
    store.set("tree-root", root.id);
    // 20 repeated peeks — all instant
    for (let i = 0; i < 20; i++) {
      const peek1 = peekContext("tree-size", "bench", store, registry);
      expect(peek1.hit).toBe(true);
      const peek2 = peekContext("tree-root", "bench", store, registry);
      expect(peek2.hit).toBe(true);
    }
  });

  it("traverse depth-3 chain, cache path, peek 30 times", () => {
    const store = new PMMemoryStore();
    const registry = new QPromiseRegistry();
    const nodes = [];
    for (let i = 0; i < 30; i++) {
      nodes.push(upsertNode("bench", "concept", `chain-${i}`, `chain node ${i}`));
    }
    for (let i = 0; i < 29; i++) {
      createRelation("bench", nodes[i].id, nodes[i + 1].id, "relates_to");
    }
    const results = retrieveWithTraversal("bench", nodes[0].id, 3);
    expect(results.length).toBe(4);
    // Cache path IDs
    const pathIds = results.map((r) => r.node.id).join(",");
    store.set("chain-path", pathIds);
    // 30 repeated peeks
    for (let i = 0; i < 30; i++) {
      const peek = peekContext("chain-path", "bench", store, registry);
      expect(peek.hit).toBe(true);
      if (peek.hit && "value" in peek) {
        expect(peek.value).toBe(pathIds);
      }
    }
  });
});

// ---------------------------------------------------------------------------
// Pattern 4: Solution engine — resolveContext with both layers active
// ---------------------------------------------------------------------------

describe("Combined: solution engine with both layers", () => {
  it("resolveContext: short-term hit after caching graph result", () => {
    const store = getStore("s1");
    // Populate graph
    upsertNode("s1", "concept", "authentication", "user login system with OAuth");
    // First resolve — hits long-term graph
    const first = resolveContext("s1", "authentication", store);
    expect(first.source).toBe("long_term");
    // Cache it in short-term
    store.set("authentication", first.value!);
    // Second resolve — hits short-term cache (faster)
    const second = resolveContext("s1", "authentication", store);
    expect(second.source).toBe("short_term");
    expect(second.score).toBe(1.0);
  });

  it("resolveContext: 20 repeated lookups after caching", () => {
    const store = getStore("s1");
    upsertNode("s1", "concept", "database", "PostgreSQL connection pooling configuration");
    const first = resolveContext("s1", "database", store);
    expect(first.source).toBe("long_term");
    store.set("database", first.value!);
    for (let i = 0; i < 20; i++) {
      const cached = resolveContext("s1", "database", store);
      expect(cached.source).toBe("short_term");
      expect(cached.score).toBe(1.0);
    }
  });

  it("promoteToLongTerm then resolveContext from both layers", () => {
    const store = getStore("s1");
    // Start with a short-term entry
    store.set("config", "app-settings-v2");
    // Promote to long-term
    const promoted = promoteToLongTerm("s1", "config", "app-settings-v2", "note");
    expect(promoted.promoted).toBe(true);
    // resolveContext should find short-term first
    const result = resolveContext("s1", "config", store);
    expect(result.source).toBe("short_term");
    expect(result.value).toBe("app-settings-v2");
    // After flushing short-term, should fall through to long-term
    store.flush();
    const fallback = resolveContext("s1", "config", store);
    expect(fallback.source).toBe("long_term");
  });

  it("getMemoryStatus reflects both layers", () => {
    const store = getStore("s1");
    store.set("k1", "v1");
    store.set("k2", "v2");
    store.set("k3", "v3");
    upsertNode("s1", "concept", "c1", "content 1");
    upsertNode("s1", "concept", "c2", "content 2");
    createRelation(
      "s1",
      getGraphStats("s1").nodes > 0 ? searchGraph("s1", "c1", 1, 1).direct[0]?.node.id ?? "" : "",
      searchGraph("s1", "c2", 1, 1).direct[0]?.node.id ?? "",
      "relates_to",
    );
    const status = getMemoryStatus("s1", store);
    expect(status.shortTerm.slots).toBe(3);
    expect(status.longTerm.nodes).toBe(2);
  });
});

// ---------------------------------------------------------------------------
// Pattern 5: Mixed workload — interleaved graph + cache operations
// ---------------------------------------------------------------------------

describe("Combined: mixed graph + cache workload", () => {
  it("alternating upsert/search/cache/peek cycle (10 iterations)", () => {
    const store = new PMMemoryStore();
    const registry = new QPromiseRegistry();
    for (let i = 0; i < 10; i++) {
      // Upsert a new node
      upsertNode("bench", "concept", `topic-${i}`, `content about topic ${i} in the knowledge graph`);
      // Search for it
      const result = searchGraph("bench", `topic ${i}`);
      expect(result.direct.length).toBeGreaterThan(0);
      // Cache the search result
      store.set(`topic-${i}`, result.direct[0].node.content);
      // Peek — instant hit
      const peek = peekContext(`topic-${i}`, "bench", store, registry);
      expect(peek.hit).toBe(true);
    }
    expect(store.size).toBe(10);
    expect(getGraphStats("bench").nodes).toBe(10);
  });

  it("build 50-node graph, cache all, peek all, flush, rebuild cache", () => {
    const store = new PMMemoryStore();
    const registry = new QPromiseRegistry();
    // Phase 1: Build graph and cache
    for (let i = 0; i < 50; i++) {
      const node = upsertNode("bench", "concept", `item-${i}`, `item ${i} data`);
      store.set(`item-${i}`, node.id);
    }
    // Phase 2: Peek all 50 from cache
    for (let i = 0; i < 50; i++) {
      const peek = peekContext(`item-${i}`, "bench", store, registry);
      expect(peek.hit).toBe(true);
    }
    // Phase 3: Flush cache
    const cleared = store.flush();
    expect(cleared).toBe(50);
    // Phase 4: All peeks are misses now
    for (let i = 0; i < 50; i++) {
      const peek = peekContext(`item-${i}`, "bench", store, registry);
      expect(peek.hit).toBe(false);
    }
    // Phase 5: Rebuild cache from graph search
    for (let i = 0; i < 50; i++) {
      const result = searchGraph("bench", `item ${i}`);
      if (result.direct.length > 0) {
        store.set(`item-${i}`, result.direct[0].node.content);
      }
    }
    // Phase 6: All peeks hit again
    for (let i = 0; i < 50; i++) {
      const peek = peekContext(`item-${i}`, "bench", store, registry);
      expect(peek.hit).toBe(true);
    }
  });

  it("10 successive resolveContext calls on populated dual-layer", () => {
    const store = getStore("s1");
    // Populate both layers
    for (let i = 0; i < 10; i++) {
      upsertNode("s1", "concept", `key-${i}`, `value for key ${i}`);
      store.set(`key-${i}`, `cached-value-${i}`);
    }
    // All 10 resolve from short-term (fastest path)
    for (let i = 0; i < 10; i++) {
      const result = resolveContext("s1", `key-${i}`, store);
      expect(result.source).toBe("short_term");
      expect(result.score).toBe(1.0);
    }
  });
});
