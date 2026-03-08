/**
 * q-promise-bridge.ts — Registry for in-flight Q-promise continuations.
 *
 * Mirrors the `QMemNode` singly-linked chain defined in
 * `Q_promise_lib/Q_promises.h`:
 *
 *     typedef struct QMemNode {
 *         long              index;
 *         const char       *payload;
 *         struct QMemNode  *next;
 *     } QMemNode;
 *
 * In the C library a chain is traversed via `q_then(head, cb)`, invoking a
 * callback for every node.  Here we model the same lifecycle in pure TypeScript:
 * each promise starts as `"pending"` (`QMemNode.payload == NULL`) and
 * transitions to `"resolved"` once `resolve()` is called with a payload.
 *
 * The `peekPromise()` method is a non-destructive status check — the
 * TypeScript equivalent of walking the chain without modifying it.
 */

/**
 * One promise entry, mirroring a single QMemNode in the chain.
 *
 * Fields:
 *   - promiseId  → logical identifier (replaces the numeric `index`)
 *   - status     → `"pending"` | `"resolved"` (NULL vs non-NULL payload)
 *   - payload    → resolved data string, or null while pending
 */
interface QPromise {
  promiseId: string;
  status: "pending" | "resolved";
  payload: string | null;
}

/** Result of a `peekPromise()` call: `[found, status, payload]`. */
export type PeekPromiseResult = [boolean, string | null, string | null];

/**
 * In-process registry of Q-promise continuations.
 *
 * Provides the same lifecycle as the C `QMemNode` chain:
 *   - `register()`     — allocate a new pending node
 *   - `resolve()`      — write the payload (analogous to q_then callback)
 *   - `peekPromise()`  — read status without consuming the entry
 *
 * Multiple sessions share a single registry; the `promiseId` is the
 * caller's responsibility to namespace (e.g. `"{sessionId}:{key}"`).
 */
export class QPromiseRegistry {
  private _promises: Map<string, QPromise> = new Map();

  // ------------------------------------------------------------------
  // Core operations
  // ------------------------------------------------------------------

  /** Add a new pending promise (allocate a QMemNode with NULL payload). */
  register(promiseId: string): void {
    this._promises.set(promiseId, {
      promiseId,
      status: "pending",
      payload: null,
    });
  }

  /**
   * Mark `promiseId` as resolved with `payload`.
   *
   * Mirrors the `QThenCallback` being invoked for a node.
   *
   * @returns true if the promise existed and was resolved; false if unknown.
   */
  resolve(promiseId: string, payload: string): boolean {
    const promise = this._promises.get(promiseId);
    if (promise === undefined) {
      return false;
    }
    promise.status = "resolved";
    promise.payload = payload;
    return true;
  }

  /**
   * Non-destructive status check.
   *
   * @returns `[found, status, payload]` — `found` is false when the promise
   * ID is unknown.
   */
  peekPromise(promiseId: string): PeekPromiseResult {
    const promise = this._promises.get(promiseId);
    if (promise === undefined) {
      return [false, null, null];
    }
    return [true, promise.status, promise.payload];
  }

  // ------------------------------------------------------------------
  // Introspection helpers
  // ------------------------------------------------------------------

  get size(): number {
    return this._promises.size;
  }

  has(promiseId: string): boolean {
    return this._promises.has(promiseId);
  }

  /** Exposed for testing: clear all promises. */
  clear(): void {
    this._promises.clear();
  }
}
