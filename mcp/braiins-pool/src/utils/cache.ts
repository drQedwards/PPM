/**
 * cache.ts — Response caching layer.
 *
 * When REDIS_ENABLED=true a Redis client is used; otherwise an in-process
 * Map provides a lightweight TTL cache that is sufficient for single-server
 * deployments.
 *
 * Default TTL: 60 seconds (configurable via constructor).
 */

import { getLogger } from './logger.js';

const logger = getLogger('cache');

interface InMemoryEntry<T> {
  value: T;
  expiresAt: number;
}

export class CacheService {
  private readonly ttlMs: number;
  private readonly store = new Map<string, InMemoryEntry<unknown>>();
  private redisClient: RedisLike | null = null;

  constructor(ttlSeconds = 60) {
    this.ttlMs = ttlSeconds * 1_000;

    const redisEnabled = process.env['REDIS_ENABLED'] === 'true';
    const redisUrl = process.env['REDIS_URL'];

    if (redisEnabled && redisUrl) {
      this.initRedis(redisUrl).catch((err) => {
        logger.warn(`Redis init failed, falling back to in-memory cache: ${err}`);
      });
    }
  }

  private async initRedis(url: string): Promise<void> {
    // Dynamic import keeps redis optional — if the package is absent the
    // in-memory fallback is used silently.
    try {
      const { createClient } = await import('redis');
      const client = createClient({ url });
      client.on('error', (err) => logger.warn(`Redis error: ${err}`));
      await client.connect();
      this.redisClient = client as unknown as RedisLike;
      logger.info('Redis cache connected');
    } catch (err) {
      logger.warn(`Could not connect to Redis: ${err}`);
    }
  }

  async get<T>(key: string): Promise<T | null> {
    if (this.redisClient) {
      try {
        const raw = await this.redisClient.get(key);
        if (raw !== null) {
          return JSON.parse(raw) as T;
        }
        return null;
      } catch {
        // fall through to in-memory
      }
    }

    const entry = this.store.get(key) as InMemoryEntry<T> | undefined;
    if (!entry) return null;
    if (Date.now() > entry.expiresAt) {
      this.store.delete(key);
      return null;
    }
    return entry.value;
  }

  async set<T>(key: string, value: T): Promise<void> {
    if (this.redisClient) {
      try {
        await this.redisClient.set(key, JSON.stringify(value), {
          PX: this.ttlMs,
        });
        return;
      } catch {
        // fall through to in-memory
      }
    }

    this.store.set(key, { value, expiresAt: Date.now() + this.ttlMs });
  }

  async invalidate(key: string): Promise<void> {
    this.store.delete(key);
    if (this.redisClient) {
      try {
        await this.redisClient.del(key);
      } catch {
        // best-effort
      }
    }
  }
}

// Minimal interface that matches both the redis client and test doubles.
interface RedisLike {
  get(key: string): Promise<string | null>;
  set(key: string, value: string, options?: { PX?: number }): Promise<unknown>;
  del(key: string): Promise<unknown>;
}
