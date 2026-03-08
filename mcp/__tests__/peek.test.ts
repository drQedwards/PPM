/**
 * peek.test.ts — Tests for peekContext() (peek.ts).
 *
 * Validates hit/miss/pending return values from the deduplication guard.
 */

import { describe, it, expect } from "vitest";
import { PMMemoryStore } from "../src/kv-store.js";
import { QPromiseRegistry } from "../src/q-promise-bridge.js";
import { peekContext } from "../src/peek.js";

function makeFixtures() {
  return {
    store: new PMMemoryStore(),
    registry: new QPromiseRegistry(),
  };
}

// ---------------------------------------------------------------------------
// peekContext tests
// ---------------------------------------------------------------------------

describe("peekContext — KV hit", () => {
  it("returns hit when key cached", () => {
    const { store, registry } = makeFixtures();
    store.set("my-key", "my-value");
    const result = peekContext("my-key", "session-1", store, registry);
    expect(result.hit).toBe(true);
    expect(result).toEqual({ hit: true, value: "my-value", index: 0 });
  });

  it("hit does not modify store", () => {
    const { store, registry } = makeFixtures();
    store.set("k", "v");
    const beforeLen = store.size;
    peekContext("k", "session-1", store, registry);
    expect(store.size).toBe(beforeLen);
  });
});

describe("peekContext — Q-promise pending", () => {
  it("returns pending when promise in flight", () => {
    const { store, registry } = makeFixtures();
    registry.register("pending-key");
    const result = peekContext("pending-key", "session-1", store, registry);
    expect(result.hit).toBe(true);
    expect(result).toEqual({
      hit: true,
      status: "pending",
      promise_id: "pending-key",
    });
  });

  it("resolved promise not returned as pending", () => {
    const { store, registry } = makeFixtures();
    registry.register("done-key");
    registry.resolve("done-key", "payload-data");
    // KV store has no entry, promise is resolved (not pending)
    const result = peekContext("done-key", "session-1", store, registry);
    expect(result.hit).toBe(false);
  });

  it("KV hit takes priority over promise", () => {
    const { store, registry } = makeFixtures();
    store.set("key", "cached-value");
    registry.register("key"); // also a pending promise
    const result = peekContext("key", "session-1", store, registry);
    expect(result.hit).toBe(true);
    expect(result).toEqual({ hit: true, value: "cached-value", index: 0 }); // KV wins
  });
});

describe("peekContext — full miss", () => {
  it("returns miss when key unknown", () => {
    const { store, registry } = makeFixtures();
    const result = peekContext("totally-new-key", "session-1", store, registry);
    expect(result).toEqual({ hit: false });
  });

  it("miss does not add to store", () => {
    const { store, registry } = makeFixtures();
    peekContext("new-key", "session-1", store, registry);
    const [hit] = store.peek("new-key");
    expect(hit).toBe(false);
  });
});
