/**
 * kv-store.test.ts — Tests for PMMemoryStore (kv-store.ts).
 *
 * Validates peek hits/misses, set, flush, and session isolation via the
 * module-level getStore / dropStore helpers.
 */

import { describe, it, expect, beforeEach } from "vitest";
import {
  PMMemoryStore,
  getStore,
  dropStore,
  _sessionStoresMap,
} from "../src/kv-store.js";

beforeEach(() => {
  _sessionStoresMap.clear();
});

// ---------------------------------------------------------------------------
// PMMemoryStore unit tests
// ---------------------------------------------------------------------------

describe("PMMemoryStore — peek", () => {
  it("peek miss on empty store", () => {
    const store = new PMMemoryStore();
    const [hit, value, index] = store.peek("missing_key");
    expect(hit).toBe(false);
    expect(value).toBeNull();
    expect(index).toBeNull();
  });

  it("peek hit after set", () => {
    const store = new PMMemoryStore();
    store.set("url", "https://example.com");
    const [hit, value, index] = store.peek("url");
    expect(hit).toBe(true);
    expect(value).toBe("https://example.com");
    expect(index).toBe(0);
  });

  it("peek index increments", () => {
    const store = new PMMemoryStore();
    store.set("a", "alpha");
    store.set("b", "beta");
    const [, , idxA] = store.peek("a");
    const [, , idxB] = store.peek("b");
    expect(idxA).toBe(0);
    expect(idxB).toBe(1);
  });

  it("peek after update returns new value", () => {
    const store = new PMMemoryStore();
    store.set("k", "old");
    store.set("k", "new");
    const [hit, value, index] = store.peek("k");
    expect(hit).toBe(true);
    expect(value).toBe("new");
    expect(index).toBe(0); // index unchanged on update
  });
});

describe("PMMemoryStore — set", () => {
  it("set returns index", () => {
    const store = new PMMemoryStore();
    const idx = store.set("foo", "bar");
    expect(idx).toBe(0);
  });

  it("set second key increments index", () => {
    const store = new PMMemoryStore();
    store.set("x", "1");
    const idx = store.set("y", "2");
    expect(idx).toBe(1);
  });

  it("set update keeps same index", () => {
    const store = new PMMemoryStore();
    store.set("k", "v1");
    const idx = store.set("k", "v2");
    expect(idx).toBe(0);
  });

  it("size after sets", () => {
    const store = new PMMemoryStore();
    expect(store.size).toBe(0);
    store.set("a", "1");
    expect(store.size).toBe(1);
    store.set("b", "2");
    expect(store.size).toBe(2);
    store.set("a", "updated"); // update, not new key
    expect(store.size).toBe(2);
  });

  it("has (contains)", () => {
    const store = new PMMemoryStore();
    store.set("present", "yes");
    expect(store.has("present")).toBe(true);
    expect(store.has("absent")).toBe(false);
  });
});

describe("PMMemoryStore — flush", () => {
  it("flush clears all slots", () => {
    const store = new PMMemoryStore();
    store.set("a", "1");
    store.set("b", "2");
    const cleared = store.flush();
    expect(cleared).toBe(2);
    expect(store.size).toBe(0);
  });

  it("flush returns zero on empty store", () => {
    const store = new PMMemoryStore();
    expect(store.flush()).toBe(0);
  });

  it("peek miss after flush", () => {
    const store = new PMMemoryStore();
    store.set("k", "v");
    store.flush();
    const [hit] = store.peek("k");
    expect(hit).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Module-level registry (session isolation)
// ---------------------------------------------------------------------------

describe("Session isolation", () => {
  it("different sessions are independent", () => {
    const s1 = getStore("session-1");
    const s2 = getStore("session-2");
    s1.set("shared_key", "session1_value");

    const [hit] = s2.peek("shared_key");
    expect(hit).toBe(false);
  });

  it("same session id returns same store", () => {
    const s1 = getStore("my-session");
    s1.set("k", "v");
    const s2 = getStore("my-session");
    const [hit, value] = s2.peek("k");
    expect(hit).toBe(true);
    expect(value).toBe("v");
  });

  it("drop store removes session", () => {
    const store = getStore("to-drop");
    store.set("k", "v");
    const cleared = dropStore("to-drop");
    expect(cleared).toBe(1);
    // A new store is created on next access
    const newStore = getStore("to-drop");
    const [hit] = newStore.peek("k");
    expect(hit).toBe(false);
  });

  it("drop nonexistent session returns zero", () => {
    expect(dropStore("ghost-session")).toBe(0);
  });

  it("silo size respected", () => {
    const store = getStore("sized-session", 512);
    expect(store.siloSize).toBe(512);
  });
});
