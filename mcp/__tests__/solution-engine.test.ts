/**
 * solution-engine.test.ts — Tests for the Context+ solution engine.
 */

import { describe, it, expect, beforeEach } from "vitest";
import { getStore, _sessionStoresMap } from "../src/kv-store.js";
import { _graphStoresMap } from "../src/memory-graph.js";
import { upsertNode } from "../src/memory-graph.js";
import { resolveContext, promoteToLongTerm, getMemoryStatus } from "../src/solution-engine.js";
import { resetVectorizer } from "../src/embeddings.js";

beforeEach(() => {
  _sessionStoresMap.clear();
  _graphStoresMap.clear();
  resetVectorizer();
});

// ---------------------------------------------------------------------------
// resolveContext
// ---------------------------------------------------------------------------

describe("resolveContext", () => {
  it("returns short_term hit when KV has the key", () => {
    const store = getStore("s1");
    store.set("url", "https://example.com");
    const result = resolveContext("s1", "url", store);
    expect(result.source).toBe("short_term");
    expect(result.value).toBe("https://example.com");
    expect(result.score).toBe(1.0);
  });

  it("returns long_term hit from memory graph", () => {
    const store = getStore("s1");
    upsertNode("s1", "concept", "authentication", "user login system with OAuth");
    const result = resolveContext("s1", "authentication", store);
    expect(result.source).toBe("long_term");
    expect(result.value).not.toBeNull();
    expect(result.score).toBeGreaterThan(0);
  });

  it("returns miss when neither layer has context", () => {
    const store = getStore("s1");
    const result = resolveContext("s1", "nonexistent_key", store);
    expect(result.source).toBe("miss");
    expect(result.value).toBeNull();
    expect(result.score).toBe(0);
  });

  it("short-term takes priority over long-term", () => {
    const store = getStore("s1");
    store.set("auth", "cached-value");
    upsertNode("s1", "concept", "auth", "graph-value");
    const result = resolveContext("s1", "auth", store);
    expect(result.source).toBe("short_term");
    expect(result.value).toBe("cached-value");
  });
});

// ---------------------------------------------------------------------------
// promoteToLongTerm
// ---------------------------------------------------------------------------

describe("promoteToLongTerm", () => {
  it("creates a memory node", () => {
    const result = promoteToLongTerm("s1", "api-key", "secret-value", "note");
    expect(result.promoted).toBe(true);
    expect(result.nodeId).toMatch(/^mn-/);
  });

  it("default node type is concept", () => {
    const result = promoteToLongTerm("s1", "config", "app configuration");
    expect(result.promoted).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// getMemoryStatus
// ---------------------------------------------------------------------------

describe("getMemoryStatus", () => {
  it("returns empty status for fresh session", () => {
    const store = getStore("s1");
    const status = getMemoryStatus("s1", store);
    expect(status.shortTerm.slots).toBe(0);
    expect(status.shortTerm.siloSize).toBe(256);
    expect(status.longTerm.nodes).toBe(0);
    expect(status.longTerm.edges).toBe(0);
    expect(status.promotionThreshold).toBe(3);
  });

  it("reflects KV and graph state", () => {
    const store = getStore("s1");
    store.set("k1", "v1");
    store.set("k2", "v2");
    upsertNode("s1", "concept", "c1", "content");
    const status = getMemoryStatus("s1", store);
    expect(status.shortTerm.slots).toBe(2);
    expect(status.longTerm.nodes).toBe(1);
  });
});
