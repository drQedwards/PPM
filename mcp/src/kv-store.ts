/**
 * kv-store.ts — In-process KV slot manager mirroring PMLL memory_silo_t semantics.
 *
 * Capacity: siloSize is enforced on set(). When at capacity and the key is new,
 * the least-recently-used (LRU) slot is evicted. Updates never grow the silo.
 *
 * Concurrency: process-local; MCP assumes single-threaded / externally serialized access.
 */

interface KVSlot {
  index: number;
  key: string;
  value: string;
  resolved: boolean;
  lastAccessed: number;
}

export type PeekResult = [boolean, string | null, number | null];

export class PMMemoryStore {
  private _slots: Map<string, KVSlot> = new Map();
  private _nextIndex = 0;
  siloSize: number;

  constructor(siloSize: number = 256) {
    this.siloSize = Math.max(1, siloSize | 0);
  }

  peek(key: string): PeekResult {
    const slot = this._slots.get(key);
    if (slot !== undefined && slot.resolved) {
      slot.lastAccessed = Date.now();
      return [true, slot.value, slot.index];
    }
    return [false, null, null];
  }

  /**
   * Store key/value. New keys at capacity evict the LRU entry.
   */
  set(key: string, value: string): number {
    const existing = this._slots.get(key);
    if (existing !== undefined) {
      existing.value = value;
      existing.resolved = true;
      existing.lastAccessed = Date.now();
      return existing.index;
    }

    if (this._slots.size >= this.siloSize) {
      this._evictLru();
    }

    const index = this._nextIndex++;
    this._slots.set(key, {
      index,
      key,
      value,
      resolved: true,
      lastAccessed: Date.now(),
    });
    return index;
  }

  private _evictLru(): void {
    let victim: string | null = null;
    let oldest = Infinity;
    for (const [k, slot] of this._slots) {
      if (slot.lastAccessed < oldest) {
        oldest = slot.lastAccessed;
        victim = k;
      }
    }
    if (victim !== null) this._slots.delete(victim);
  }

  flush(): number {
    const count = this._slots.size;
    this._slots.clear();
    this._nextIndex = 0;
    return count;
  }

  get size(): number {
    return this._slots.size;
  }

  has(key: string): boolean {
    return this._slots.has(key);
  }
}

const _sessionStores: Map<string, PMMemoryStore> = new Map();

export function getStore(sessionId: string, siloSize: number = 256): PMMemoryStore {
  let store = _sessionStores.get(sessionId);
  if (store === undefined) {
    store = new PMMemoryStore(siloSize);
    _sessionStores.set(sessionId, store);
  }
  return store;
}

export function dropStore(sessionId: string): number {
  const store = _sessionStores.get(sessionId);
  _sessionStores.delete(sessionId);
  return store !== undefined ? store.size : 0;
}

/** Clear existing silo and return a fresh store (clear_on_init). */
export function resetStore(sessionId: string, siloSize: number = 256): PMMemoryStore {
  _sessionStores.delete(sessionId);
  const store = new PMMemoryStore(siloSize);
  _sessionStores.set(sessionId, store);
  return store;
}

export const _sessionStoresMap = _sessionStores;
