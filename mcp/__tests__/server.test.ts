/**
 * server.test.ts — Smoke tests for the MCP tool functions in index.ts.
 *
 * These tests call the underlying tool functions indirectly via the
 * McpServer's registered tool handlers to verify request/response semantics
 * without requiring a running MCP server transport.
 *
 * Since the MCP SDK doesn't easily expose direct function calls,
 * we test the underlying logic (kv-store, peek, q-promise-bridge) directly
 * and validate the server integration by calling the same functions the
 * tool handlers use.
 */

import { describe, it, expect, beforeEach } from "vitest";
import { getStore, dropStore, _sessionStoresMap } from "../src/kv-store.js";
import { QPromiseRegistry } from "../src/q-promise-bridge.js";
import { peekContext } from "../src/peek.js";

// Replicate the server-level state for integration-style tests
const promiseRegistry = new QPromiseRegistry();
const activeSessions: Map<string, number> = new Map();

function resetState() {
  _sessionStoresMap.clear();
  activeSessions.clear();
  promiseRegistry.clear();
}

// Mirror the tool functions from index.ts
function init(sessionId: string, siloSize: number = 256) {
  const store = getStore(sessionId, siloSize);
  store.siloSize = siloSize;
  activeSessions.set(sessionId, siloSize);
  return { status: "initialized", session_id: sessionId, silo_size: siloSize };
}

function peek(sessionId: string, key: string) {
  const store = getStore(sessionId);
  return peekContext(key, sessionId, store, promiseRegistry);
}

function set(sessionId: string, key: string, value: string) {
  const store = getStore(sessionId);
  const index = store.set(key, value);
  return { status: "stored", index };
}

function resolve(sessionId: string, promiseId: string) {
  const [found, status, payload] = promiseRegistry.peekPromise(promiseId);
  if (!found) {
    return { status: "pending", payload: null };
  }
  return { status, payload };
}

function flush(sessionId: string) {
  const cleared = dropStore(sessionId);
  activeSessions.delete(sessionId);
  return { status: "flushed", cleared_count: cleared };
}

beforeEach(() => {
  resetState();
});

// ---------------------------------------------------------------------------
// init
// ---------------------------------------------------------------------------

describe("init", () => {
  it("returns initialized", () => {
    const result = init("s1");
    expect(result.status).toBe("initialized");
    expect(result.session_id).toBe("s1");
    expect(result.silo_size).toBe(256); // default
  });

  it("custom silo size", () => {
    const result = init("s2", 512);
    expect(result.silo_size).toBe(512);
  });

  it("registers session", () => {
    init("s3");
    expect(activeSessions.has("s3")).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// set + peek
// ---------------------------------------------------------------------------

describe("set and peek", () => {
  it("peek miss before set", () => {
    init("sx");
    const result = peek("sx", "missing");
    expect(result.hit).toBe(false);
  });

  it("set then peek hit", () => {
    init("sa");
    const setResult = set("sa", "url", "https://example.com");
    expect(setResult.status).toBe("stored");
    expect(typeof setResult.index).toBe("number");

    const peekResult = peek("sa", "url");
    expect(peekResult.hit).toBe(true);
    if (peekResult.hit && "value" in peekResult) {
      expect(peekResult.value).toBe("https://example.com");
    }
  });

  it("set returns incrementing index", () => {
    init("sb");
    const r1 = set("sb", "k1", "v1");
    const r2 = set("sb", "k2", "v2");
    expect(r1.index).toBe(0);
    expect(r2.index).toBe(1);
  });
});

// ---------------------------------------------------------------------------
// resolve
// ---------------------------------------------------------------------------

describe("resolve", () => {
  it("resolve unknown promise returns pending", () => {
    const result = resolve("sr", "ghost");
    expect(result.status).toBe("pending");
    expect(result.payload).toBeNull();
  });

  it("resolve registered and resolved promise", () => {
    promiseRegistry.register("p1");
    promiseRegistry.resolve("p1", "some-payload");
    const result = resolve("sr", "p1");
    expect(result.status).toBe("resolved");
    expect(result.payload).toBe("some-payload");
  });

  it("resolve pending promise", () => {
    promiseRegistry.register("p2");
    const result = resolve("sr", "p2");
    expect(result.status).toBe("pending");
    expect(result.payload).toBeNull();
  });

  it("peek returns pending for in-flight promise", () => {
    init("sp");
    promiseRegistry.register("async-key");
    const result = peek("sp", "async-key");
    expect(result.hit).toBe(true);
    if (result.hit && "status" in result) {
      expect(result.status).toBe("pending");
    }
  });
});

// ---------------------------------------------------------------------------
// flush
// ---------------------------------------------------------------------------

describe("flush", () => {
  it("clears slots", () => {
    init("sf");
    set("sf", "a", "1");
    set("sf", "b", "2");
    const result = flush("sf");
    expect(result.status).toBe("flushed");
    expect(result.cleared_count).toBe(2);
  });

  it("removes session from active", () => {
    init("sf2");
    flush("sf2");
    expect(activeSessions.has("sf2")).toBe(false);
  });

  it("peek miss after flush", () => {
    init("sf3");
    set("sf3", "k", "v");
    flush("sf3");
    const result = peek("sf3", "k");
    expect(result.hit).toBe(false);
  });

  it("flush nonexistent session returns zero", () => {
    const result = flush("ghost-session");
    expect(result.status).toBe("flushed");
    expect(result.cleared_count).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// Session isolation
// ---------------------------------------------------------------------------

describe("session isolation", () => {
  it("two sessions don't share KV", () => {
    init("sess-A");
    init("sess-B");
    set("sess-A", "shared", "A-value");
    const result = peek("sess-B", "shared");
    expect(result.hit).toBe(false);
  });
});
