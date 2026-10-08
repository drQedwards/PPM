/**
 * q-promise-bridge.ts — In-process registry for in-flight Q-promise work.
 *
 * A small TypeScript model of the promise lifecycle in Q_promise_lib
 * (`qpromise.h`): an entry starts `"pending"` and becomes `"resolved"` once
 * `resolve()` stores a payload. It does not call the C library, and it only
 * models PENDING -> RESOLVED; the C API also has REJECTED / CANCELLED and
 * then / catch / finally continuations that run in `qpromise_drain()`.
 *
 * The older `QMemNode` / `q_mem_create_chain` / `q_then` chain API that this
 * module used to describe was removed from Q_promise_lib. Python bindings for
 * the real library: `Q_promise_lib/Q_promises.py` (ctypes) and `Q_promises.pyx`.
 *
 * `peekPromise()` is a non-destructive status check.
 */

/**
 * One promise entry (a pending or resolved unit of work).
 *
 * Fields:
 *   - promiseId  → logical identifier (callers namespace it, e.g. `"{sessionId}:{key}"`)
 *   - status     → `"pending"` | `"resolved"` (QPROMISE_PENDING / QPROMISE_RESOLVED)
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
 * Models the pending -> resolved part of the C `qpromise_t` lifecycle:
 *   - `register()`     — allocate a new pending node
 *   - `resolve()`      — store the payload (like `qpromise_resolve`)
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

  /** Add a new pending promise (like `qpromise_create`). */
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
   * Like `qpromise_resolve`; there are no continuations to run here.
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
