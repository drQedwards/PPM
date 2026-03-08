/**
 * kv-store.ts — In-process KV slot manager mirroring PMLL memory_silo_t semantics.
 *
 * This module provides a pure-TypeScript KV store whose slot structure mirrors the
 * `memory_silo_t` type defined in PMLL.h:
 *
 *     typedef struct {
 *         int *tree;
 *         int  size;
 *     } memory_silo_t;
 *
 * Each KV slot tracks an index (position in the silo), the string key, the
 * string value, and a `resolved` flag — analogous to `init_silo()`
 * allocating slots and `update_silo()` writing values into them
 * (PMLL.c::init_silo / PMLL.c::update_silo).
 *
 * Session isolation is achieved by keying stores on `sessionId`, so
 * parallel agent tasks cannot interfere with each other.
 */

/**
 * A single KV slot, mirroring one entry in memory_silo_t.
 *
 * Fields parallel PMLL.c::update_silo(silo, var, value, depth):
 *   - index    → position in the silo tree array
 *   - key      → symbolic variable name
 *   - value    → stored value string
 *   - resolved → true once a value has been committed (update_silo called)
 */
interface KVSlot {
  index: number;
  key: string;
  value: string;
  resolved: boolean;
}

/** Result of a `peek()` call: `[hit, value, index]`. */
export type PeekResult = [boolean, string | null, number | null];

/**
 * Per-session KV store mirroring PMLL memory_silo_t.
 *
 * Mirrors the C-level silo initialised by `PMLL.c::init_silo()` and
 * written to by `PMLL.c::update_silo()`.  This pure-TypeScript
 * implementation keeps the same conceptual slot structure while
 * remaining dependency-free at runtime (no C compilation required).
 *
 * Each instance represents one session's isolated memory silo.
 * A module-level registry keyed by `sessionId` is maintained by the
 * server layer.
 */
export class PMMemoryStore {
  /** Maps key → KVSlot; order of insertion gives the slot index.
   *  Mirrors the tree array in memory_silo_t (PMLL.h). */
  private _slots: Map<string, KVSlot> = new Map();

  siloSize: number;

  constructor(siloSize: number = 256) {
    this.siloSize = siloSize;
  }

  // ------------------------------------------------------------------
  // Core operations
  // ------------------------------------------------------------------

  /**
   * Non-destructive existence check — analogous to reading the silo tree.
   *
   * @returns `[hit, value, index]` where `hit` is true when the key is cached.
   */
  peek(key: string): PeekResult {
    const slot = this._slots.get(key);
    if (slot !== undefined && slot.resolved) {
      return [true, slot.value, slot.index];
    }
    return [false, null, null];
  }

  /**
   * Store key/value, allocating a new slot index if needed.
   *
   * Mirrors PMLL.c::update_silo() writing a var/value pair into the
   * silo tree at the computed depth.
   *
   * @returns The slot index for the stored entry.
   */
  set(key: string, value: string): number {
    const existing = this._slots.get(key);
    if (existing !== undefined) {
      // Update existing slot in-place (Ouroboros cache update).
      existing.value = value;
      existing.resolved = true;
      return existing.index;
    }

    const index = this._slots.size;
    this._slots.set(key, { index, key, value, resolved: true });
    return index;
  }

  /**
   * Clear all KV slots for this session.
   *
   * @returns The number of slots that were cleared.
   */
  flush(): number {
    const count = this._slots.size;
    this._slots.clear();
    return count;
  }

  // ------------------------------------------------------------------
  // Introspection helpers
  // ------------------------------------------------------------------

  get size(): number {
    return this._slots.size;
  }

  has(key: string): boolean {
    return this._slots.has(key);
  }
}

// Module-level registry: sessionId → PMMemoryStore
// Mirrors the global silo pool managed by pml_t in PMLL.h.
const _sessionStores: Map<string, PMMemoryStore> = new Map();

/** Return (or lazily create) the store for `sessionId`. */
export function getStore(sessionId: string, siloSize: number = 256): PMMemoryStore {
  let store = _sessionStores.get(sessionId);
  if (store === undefined) {
    store = new PMMemoryStore(siloSize);
    _sessionStores.set(sessionId, store);
  }
  return store;
}

/** Remove the store for `sessionId`, returning the cleared slot count. */
export function dropStore(sessionId: string): number {
  const store = _sessionStores.get(sessionId);
  _sessionStores.delete(sessionId);
  return store !== undefined ? store.size : 0;
}

/** Exposed for testing: direct access to the session store registry. */
export const _sessionStoresMap = _sessionStores;
