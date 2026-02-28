/**
 * tests/ratelimit.test.ts — Unit tests for the RateLimiter.
 */

import { RateLimiter } from '../src/utils/ratelimit.js';

describe('RateLimiter', () => {
  it('resolves immediately for the first acquire', async () => {
    const limiter = new RateLimiter(100); // 100 rps → 10 ms interval
    const start = Date.now();
    await limiter.acquire();
    expect(Date.now() - start).toBeLessThan(50);
  });

  it('serialises concurrent acquires', async () => {
    const limiter = new RateLimiter(1000); // 1 ms interval
    const results: number[] = [];
    // Fire 3 concurrent acquires; each should resolve in order
    await Promise.all([
      limiter.acquire().then(() => results.push(1)),
      limiter.acquire().then(() => results.push(2)),
      limiter.acquire().then(() => results.push(3)),
    ]);
    expect(results).toEqual([1, 2, 3]);
  });
});
