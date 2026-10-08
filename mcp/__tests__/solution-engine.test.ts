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

// ---------------------------------------------------------------------------
// resolveContext: exact label lookup + semantic threshold
// ---------------------------------------------------------------------------

describe("resolveContext exact label and min score", () => {
  const SHA_A = "build:b70a337709832f585bc8ad4464182e34ef3cd9bf5d96826b34bede83379248bc";
  const SHA_NEVER = "build:5f0c2a9e7d4b1c3a8e6f2d0b9a7c5e3f1d8b6a4c2e0f9d7b5a3c1e8f6d4b2a0c";

  function populate(): void {
    upsertNode("s1", "file", SHA_A, '{"status":"ok","w":0}');
    upsertNode("s1", "note", "build:6d31470f6c8b", "Batch build: 28/58 units OK; 10 CUDA units skipped.");
    upsertNode("s1", "concept", "module:Panda", "Panda: kinds=c,pyx; failing=Panda.c");
  }

  it("a never-stored key is a miss, not the nearest node", () => {
    populate();
    const store = getStore("s1");
    const r = resolveContext("s1", SHA_NEVER, store);
    expect(r.source).toBe("miss");
    expect(r.value).toBeNull();
    expect(r.match).toBeNull();
  });

  it("an exact label returns that node with score 1", () => {
    populate();
    const r = resolveContext("s1", SHA_A, getStore("s1"));
    expect(r.source).toBe("long_term");
    expect(r.match).toBe("exact");
    expect(r.score).toBe(1);
    expect(r.value).toBe('{"status":"ok","w":0}');
    expect(r.nodeId).toMatch(/^mn-/);
  });

  it("exact label beats a semantically closer node", () => {
    upsertNode("s1", "concept", "auth", "graph-value");
    upsertNode("s1", "concept", "auth login", "auth auth auth login");
    const r = resolveContext("s1", "auth", getStore("s1"));
    expect(r.match).toBe("exact");
    expect(r.value).toBe("graph-value");
  });

  it("semantic hits above the threshold still resolve", () => {
    upsertNode("s1", "concept", "database pooling", "PostgreSQL connection pooling configuration");
    const r = resolveContext("s1", "PostgreSQL connection pooling configuration", getStore("s1"));
    expect(r.source).toBe("long_term");
    expect(r.match).toBe("semantic");
    expect(r.score).toBeGreaterThanOrEqual(0.5);
  });

  it("min_score controls the semantic fallback", () => {
    populate();
    const store = getStore("s1");
    expect(resolveContext("s1", SHA_NEVER, store, 0).source).toBe("long_term");
    expect(resolveContext("s1", SHA_NEVER, store, 0).match).toBe("semantic");
    expect(resolveContext("s1", SHA_NEVER, store, 1).source).toBe("miss");
  });

  it("an empty graph is a miss at any threshold", () => {
    expect(resolveContext("s1", "anything", getStore("s1"), 0).source).toBe("miss");
  });
});
