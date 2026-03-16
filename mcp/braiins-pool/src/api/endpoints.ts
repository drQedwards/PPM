/**
 * endpoints.ts — Braiins Pool API endpoint mappings.
 */

export const ENDPOINTS = {
  // Worker endpoints
  WORKERS: '/workers',
  WORKER_DETAILS: (name: string) => `/workers/${encodeURIComponent(name)}`,
  WORKER_HASHRATE: (name: string) => `/workers/${encodeURIComponent(name)}/hashrate`,

  // Earnings & payout endpoints
  EARNINGS: '/earnings',
  PAYOUTS: '/payouts',

  // Pool statistics endpoints
  POOL_STATS: '/pool/stats',
  BLOCK_HISTORY: '/pool/blocks',
  NETWORK_DIFFICULTY: '/network/difficulty',

  // User configuration endpoints
  PAYOUT_THRESHOLD: '/settings/payout-threshold',
  NOTIFICATIONS: '/settings/notifications',
} as const;
