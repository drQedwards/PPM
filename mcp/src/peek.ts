/**
 * peek.ts — Main guard function for MCP context deduplication.
 *
 * `peekContext()` is the primary primitive that agents call **before**
 * any expensive MCP tool invocation (e.g. a Playwright navigation or a
 * remote API call).  It checks two layers:
 *
 * 1. The in-process KV store (`PMMemoryStore`) — analogous to reading the
 *    PMLL memory silo (PMLL.c::init_silo / update_silo) for a cached result.
 * 2. The Q-promise registry (`QPromiseRegistry`) — analogous to checking
 *    whether a `QMemNode` chain is still in-flight (Q_promise_lib pending).
 *
 * If both layers miss, the caller is expected to proceed with the real tool
 * call and then invoke `store.set(key, value)` to populate the cache for
 * future agents.
 */

import { PMMemoryStore } from "./kv-store.js";
import { QPromiseRegistry } from "./q-promise-bridge.js";

/** Return shape for a KV cache hit. */
export interface PeekHitResult {
  hit: true;
  value: string;
  index: number;
}

/** Return shape for a Q-promise pending hit. */
export interface PeekPendingResult {
  hit: true;
  status: "pending";
  promise_id: string;
}

/** Return shape for a full miss. */
export interface PeekMissResult {
  hit: false;
}

export type PeekContextResult = PeekHitResult | PeekPendingResult | PeekMissResult;

/**
 * Check whether `key` is already resolved for `sessionId`.
 *
 * The function implements a two-stage guard:
 *
 * Stage 1 — KV store hit (PMLL silo cache):
 *     If the key exists and is resolved, return the cached value
 *     immediately.  This eliminates the need to re-invoke the
 *     corresponding MCP tool entirely.
 *
 * Stage 2 — Q-promise pending check:
 *     If the key is registered as an in-flight promise, return a
 *     `pending` indicator so the caller can await resolution rather
 *     than launching a duplicate tool call.
 *
 * Stage 3 — Full miss:
 *     Neither layer has seen this key.  The caller should proceed with
 *     the real MCP tool call and then call `store.set(key, value)`
 *     to populate the cache.
 *
 * @param key              The context key to look up (e.g. a URL, task ID).
 * @param sessionId        Identifies the current agent session (for logging).
 * @param store            The session's `PMMemoryStore` instance.
 * @param promiseRegistry  Shared `QPromiseRegistry` instance.
 *
 * @returns One of:
 *   - `{ hit: true, value: string, index: number }`          — KV hit
 *   - `{ hit: true, status: "pending", promise_id: string }` — in-flight
 *   - `{ hit: false }`                                        — full miss
 */
export function peekContext(
  key: string,
  sessionId: string,
  store: PMMemoryStore,
  promiseRegistry: QPromiseRegistry,
): PeekContextResult {
  // Stage 1: KV store check (PMLL silo read)
  const [hit, value, index] = store.peek(key);
  if (hit) {
    return { hit: true, value: value!, index: index! };
  }

  // Stage 2: Q-promise in-flight check
  const [found, status] = promiseRegistry.peekPromise(key);
  if (found && status === "pending") {
    return { hit: true, status: "pending", promise_id: key };
  }

  // Stage 3: Full miss — caller proceeds with the actual tool call
  return { hit: false };
}
