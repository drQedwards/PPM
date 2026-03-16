/**
 * tests/cache.test.ts — Unit tests for the CacheService.
 */

import { jest } from '@jest/globals';
import { CacheService } from '../src/utils/cache.js';

describe('CacheService (in-memory)', () => {
  let cache: CacheService;

  beforeEach(() => {
    // Use a very short TTL so expiry can be tested with fake timers
    cache = new CacheService(1);
  });

  it('returns null for unknown keys', async () => {
    const result = await cache.get('missing');
    expect(result).toBeNull();
  });

  it('returns stored value on cache hit', async () => {
    await cache.set('key', { foo: 'bar' });
    const result = await cache.get('key');
    expect(result).toEqual({ foo: 'bar' });
  });

  it('returns null after TTL expires', async () => {
    jest.useFakeTimers();
    await cache.set('ttl-key', 'value');
    jest.advanceTimersByTime(2_000); // advance past 1 s TTL
    const result = await cache.get('ttl-key');
    expect(result).toBeNull();
    jest.useRealTimers();
  });

  it('invalidate removes the entry', async () => {
    await cache.set('del-key', 42);
    await cache.invalidate('del-key');
    expect(await cache.get('del-key')).toBeNull();
  });
});
