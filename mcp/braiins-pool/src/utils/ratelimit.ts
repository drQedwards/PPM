/**
 * ratelimit.ts — Simple token-bucket rate limiter for outbound API requests.
 *
 * Defaults to 10 requests per second (configurable), which comfortably fits
 * within Braiins Pool's undocumented rate limits while allowing burst usage.
 */

export class RateLimiter {
  private readonly intervalMs: number;
  private lastCallAt = 0;
  private queue: Array<() => void> = [];
  private timer: ReturnType<typeof setTimeout> | null = null;

  /**
   * @param requestsPerSecond - Maximum requests allowed per second.
   */
  constructor(requestsPerSecond = 10) {
    this.intervalMs = 1_000 / requestsPerSecond;
  }

  /**
   * Acquire a slot before making an API request.
   * Resolves immediately if within rate limits, otherwise queues
   * the caller and resolves after the appropriate delay.
   */
  acquire(): Promise<void> {
    return new Promise((resolve) => {
      this.queue.push(resolve);
      if (this.timer === null) {
        this.drainQueue();
      }
    });
  }

  private drainQueue(): void {
    const next = this.queue.shift();
    if (!next) {
      this.timer = null;
      return;
    }

    const now = Date.now();
    const wait = Math.max(0, this.lastCallAt + this.intervalMs - now);

    this.timer = setTimeout(() => {
      this.lastCallAt = Date.now();
      next();
      this.drainQueue();
    }, wait);
  }
}
