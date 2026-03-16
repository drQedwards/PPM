/**
 * client.ts — HTTP request wrapper for the Braiins Pool REST API.
 *
 * Handles authentication, base URL configuration, error translation,
 * and optional response caching via the cache utility.
 */

import axios, { AxiosInstance } from 'axios';
import { getLogger } from '../utils/logger.js';
import { CacheService } from '../utils/cache.js';
import { RateLimiter } from '../utils/ratelimit.js';

const logger = getLogger('api-client');

export class BraiinsApiClient {
  private readonly http: AxiosInstance;
  private readonly cache: CacheService;
  private readonly rateLimiter: RateLimiter;

  constructor(
    apiKey: string,
    baseUrl: string = 'https://pool.braiins.com/api/v1',
    cache?: CacheService,
    rateLimiter?: RateLimiter,
    httpInstance?: AxiosInstance,
  ) {
    this.http = httpInstance ?? axios.create({
      baseURL: baseUrl,
      headers: {
        'SlushPool-Auth-Token': apiKey,
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      timeout: 30_000,
    });
    this.cache = cache ?? new CacheService();
    this.rateLimiter = rateLimiter ?? new RateLimiter();
  }

  async get<T>(path: string, cacheKey?: string): Promise<T> {
    const key = cacheKey ?? path;

    const cached = await this.cache.get<T>(key);
    if (cached !== null) {
      logger.debug(`Cache hit: ${key}`);
      return cached;
    }

    await this.rateLimiter.acquire();

    try {
      logger.debug(`GET ${path}`);
      const response = await this.http.get<T>(path);
      await this.cache.set(key, response.data);
      return response.data;
    } catch (err) {
      throw this.translateError(err);
    }
  }

  async post<T>(path: string, body: unknown): Promise<T> {
    await this.rateLimiter.acquire();

    try {
      logger.debug(`POST ${path}`);
      const response = await this.http.post<T>(path, body);
      return response.data;
    } catch (err) {
      throw this.translateError(err);
    }
  }

  async put<T>(path: string, body: unknown): Promise<T> {
    await this.rateLimiter.acquire();

    try {
      logger.debug(`PUT ${path}`);
      const response = await this.http.put<T>(path, body);
      return response.data;
    } catch (err) {
      throw this.translateError(err);
    }
  }

  private translateError(err: unknown): Error {
    // Duck-type the AxiosError rather than using instanceof so that the check
    // works correctly across different module instances (e.g. ts-jest ESM).
    const axiosErr = err as { isAxiosError?: boolean; response?: { status?: number; data?: unknown }; message?: string };
    if (axiosErr?.isAxiosError) {
      const status = axiosErr.response?.status;
      const data = axiosErr.response?.data as { message?: string } | undefined;
      const message = data?.message ?? (err instanceof Error ? err.message : String(err));
      if (status === 401) {
        return new Error(`Authentication failed: invalid or missing BRAIINS_API_KEY`);
      }
      if (status === 404) {
        return new Error(`Resource not found: ${message}`);
      }
      if (status === 429) {
        return new Error(`Rate limit exceeded — please retry after a moment`);
      }
      return new Error(`Braiins API error (${status ?? 'network'}): ${message}`);
    }
    return err instanceof Error ? err : new Error(String(err));
  }
}
