/**
 * tests/client.test.ts — Unit tests for BraiinsApiClient.
 *
 * Uses axios-mock-adapter to intercept HTTP calls so no real network
 * requests are made.
 */

import axios from 'axios';
import MockAdapter from 'axios-mock-adapter';
import { BraiinsApiClient } from '../src/api/client.js';
import { CacheService } from '../src/utils/cache.js';
import { RateLimiter } from '../src/utils/ratelimit.js';

// Create a single axios instance and attach the mock adapter to it.
// We inject this instance into the client so the mock intercepts requests.
const httpInstance = axios.create({ baseURL: 'https://pool.braiins.com/api/v1' });
const mockAxios = new MockAdapter(httpInstance);

function makeClient(): BraiinsApiClient {
  return new BraiinsApiClient(
    'test-api-key',
    'https://pool.braiins.com/api/v1',
    new CacheService(60),
    new RateLimiter(1000),
    httpInstance,
  );
}

afterEach(() => {
  mockAxios.reset();
});

afterAll(() => {
  mockAxios.restore();
});

describe('BraiinsApiClient.get', () => {
  it('returns parsed JSON on 200', async () => {
    mockAxios.onGet('/workers').reply(200, { workers: [] });
    const client = makeClient();
    const data = await client.get<{ workers: unknown[] }>('/workers');
    expect(data).toEqual({ workers: [] });
  });

  it('throws authentication error on 401', async () => {
    mockAxios.onGet('/workers').reply(401, { message: 'Unauthorized' });
    const client = makeClient();
    await expect(client.get('/workers')).rejects.toThrow(/Authentication failed/);
  });

  it('throws not-found error on 404', async () => {
    mockAxios.onGet('/workers/ghost').reply(404, { message: 'Not found' });
    const client = makeClient();
    await expect(client.get('/workers/ghost')).rejects.toThrow(/not found/i);
  });

  it('throws rate-limit error on 429', async () => {
    mockAxios.onGet('/pool/stats').reply(429, {});
    const client = makeClient();
    await expect(client.get('/pool/stats')).rejects.toThrow(/Rate limit/);
  });

  it('returns cached value on second call', async () => {
    let callCount = 0;
    mockAxios.onGet('/pool/stats').reply(() => {
      callCount++;
      return [200, { total_hashrate: '100 EH/s' }];
    });
    const client = makeClient();
    await client.get('/pool/stats');
    await client.get('/pool/stats'); // should hit cache
    expect(callCount).toBe(1);
  });
});

describe('BraiinsApiClient.post', () => {
  it('sends body and returns response', async () => {
    mockAxios.onPost('/workers/miner-01/restart').reply(200, { success: true });
    const client = makeClient();
    const result = await client.post<{ success: boolean }>('/workers/miner-01/restart', {});
    expect(result).toEqual({ success: true });
  });
});
