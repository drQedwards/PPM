/**
 * tools.ts — Tool definitions and handlers for the Braiins Pool MCP server.
 *
 * Tools are organised into four groups matching the problem specification:
 *   1. Worker Management
 *   2. Earnings & Payouts
 *   3. Pool Statistics
 *   4. Configuration
 */

import { z } from 'zod';
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { BraiinsApiClient } from '../api/client.js';
import { ENDPOINTS } from '../api/endpoints.js';
import type {
  Worker,
  WorkerDetails,
  TimeSeries,
  EarningsSummary,
  Payout,
  PayoutEstimate,
  PoolStats,
  Block,
  NotificationConfig,
} from '../api/types.js';
import { getLogger } from '../utils/logger.js';

const logger = getLogger('tools');

// ---------------------------------------------------------------------------
// Registration helper
// ---------------------------------------------------------------------------

export function registerTools(server: McpServer, client: BraiinsApiClient): void {
  registerWorkerTools(server, client);
  registerEarningsTools(server, client);
  registerPoolStatTools(server, client);
  registerConfigTools(server, client);
  logger.info('All tools registered');
}

// ---------------------------------------------------------------------------
// 1. Worker Management
// ---------------------------------------------------------------------------

function registerWorkerTools(server: McpServer, client: BraiinsApiClient): void {
  server.tool(
    'list_workers',
    'Get all configured workers and their current status',
    {
      user_id: z.string().optional().describe('Optional user ID filter'),
    },
    async ({ user_id }) => {
      const path = user_id
        ? `${ENDPOINTS.WORKERS}?user_id=${encodeURIComponent(user_id)}`
        : ENDPOINTS.WORKERS;
      const data = await client.get<{ workers: Worker[] }>(path);
      return {
        content: [{ type: 'text', text: JSON.stringify(data, null, 2) }],
      };
    },
  );

  server.tool(
    'get_worker_details',
    'Get detailed stats for a specific worker',
    {
      worker_name: z.string().describe('Name of the worker'),
    },
    async ({ worker_name }) => {
      const data = await client.get<WorkerDetails>(ENDPOINTS.WORKER_DETAILS(worker_name));
      return {
        content: [{ type: 'text', text: JSON.stringify(data, null, 2) }],
      };
    },
  );

  server.tool(
    'get_worker_hashrate',
    'Get historical hashrate chart data for a worker',
    {
      worker_name: z.string().describe('Name of the worker'),
      start_date: z.string().describe('Start date in ISO 8601 format (e.g. 2024-12-01T00:00:00Z)'),
      end_date: z.string().describe('End date in ISO 8601 format (e.g. 2024-12-31T23:59:59Z)'),
    },
    async ({ worker_name, start_date, end_date }) => {
      const path =
        `${ENDPOINTS.WORKER_HASHRATE(worker_name)}` +
        `?start=${encodeURIComponent(start_date)}&end=${encodeURIComponent(end_date)}`;
      const data = await client.get<TimeSeries>(path);
      return {
        content: [{ type: 'text', text: JSON.stringify(data, null, 2) }],
      };
    },
  );

  server.tool(
    'restart_worker',
    'Remotely restart a worker (if supported by the pool)',
    {
      worker_name: z.string().describe('Name of the worker to restart'),
    },
    async ({ worker_name }) => {
      const data = await client.post<{ success: boolean }>(
        `${ENDPOINTS.WORKER_DETAILS(worker_name)}/restart`,
        {},
      );
      return {
        content: [{ type: 'text', text: JSON.stringify(data, null, 2) }],
      };
    },
  );
}

// ---------------------------------------------------------------------------
// 2. Earnings & Payouts
// ---------------------------------------------------------------------------

function registerEarningsTools(server: McpServer, client: BraiinsApiClient): void {
  server.tool(
    'get_earnings_summary',
    'Get total unpaid balance and earnings history',
    {
      currency: z
        .enum(['BTC', 'USD'])
        .optional()
        .describe('Currency for amounts (default: BTC)'),
    },
    async ({ currency }) => {
      const path = currency
        ? `${ENDPOINTS.EARNINGS}?currency=${currency}`
        : ENDPOINTS.EARNINGS;
      const data = await client.get<EarningsSummary>(path);
      return {
        content: [{ type: 'text', text: JSON.stringify(data, null, 2) }],
      };
    },
  );

  server.tool(
    'get_payout_history',
    'Get past payout transactions',
    {
      limit: z.number().int().positive().optional().describe('Maximum number of results'),
      offset: z.number().int().nonnegative().optional().describe('Pagination offset'),
    },
    async ({ limit, offset }) => {
      const params = new URLSearchParams();
      if (limit !== undefined) params.set('limit', String(limit));
      if (offset !== undefined) params.set('offset', String(offset));
      const qs = params.toString();
      const path = qs ? `${ENDPOINTS.PAYOUTS}?${qs}` : ENDPOINTS.PAYOUTS;
      const data = await client.get<{ payouts: Payout[] }>(path);
      return {
        content: [{ type: 'text', text: JSON.stringify(data, null, 2) }],
      };
    },
  );

  server.tool(
    'estimate_next_payout',
    'Estimate the projected time and amount of the next payout',
    {
      current_hashrate: z.number().positive().describe('Current hashrate in TH/s'),
    },
    async ({ current_hashrate }) => {
      const path = `${ENDPOINTS.PAYOUTS}/estimate?hashrate=${current_hashrate}`;
      const data = await client.get<PayoutEstimate>(path);
      return {
        content: [{ type: 'text', text: JSON.stringify(data, null, 2) }],
      };
    },
  );
}

// ---------------------------------------------------------------------------
// 3. Pool Statistics
// ---------------------------------------------------------------------------

function registerPoolStatTools(server: McpServer, client: BraiinsApiClient): void {
  server.tool(
    'get_pool_stats',
    'Get network-wide pool metrics (hashrate, luck, fee, active workers)',
    {},
    async () => {
      const data = await client.get<PoolStats>(ENDPOINTS.POOL_STATS);
      return {
        content: [{ type: 'text', text: JSON.stringify(data, null, 2) }],
      };
    },
  );

  server.tool(
    'get_block_history',
    'Get recent blocks discovered by the pool',
    {
      limit: z.number().int().positive().optional().describe('Maximum number of blocks to return'),
    },
    async ({ limit }) => {
      const path = limit
        ? `${ENDPOINTS.BLOCK_HISTORY}?limit=${limit}`
        : ENDPOINTS.BLOCK_HISTORY;
      const data = await client.get<{ blocks: Block[] }>(path);
      return {
        content: [{ type: 'text', text: JSON.stringify(data, null, 2) }],
      };
    },
  );

  server.tool(
    'get_network_difficulty',
    'Get the current Bitcoin network difficulty',
    {},
    async () => {
      const data = await client.get<{ difficulty: number }>(ENDPOINTS.NETWORK_DIFFICULTY);
      return {
        content: [{ type: 'text', text: JSON.stringify(data, null, 2) }],
      };
    },
  );
}

// ---------------------------------------------------------------------------
// 4. Configuration
// ---------------------------------------------------------------------------

function registerConfigTools(server: McpServer, client: BraiinsApiClient): void {
  server.tool(
    'update_payout_threshold',
    'Set the minimum payout amount',
    {
      threshold: z.number().positive().describe('Minimum payout threshold'),
      currency: z.string().describe('Currency code (e.g. BTC)'),
    },
    async ({ threshold, currency }) => {
      const data = await client.put<{ success: boolean }>(ENDPOINTS.PAYOUT_THRESHOLD, {
        threshold,
        currency,
      });
      return {
        content: [{ type: 'text', text: JSON.stringify(data, null, 2) }],
      };
    },
  );

  server.tool(
    'set_notification_preferences',
    'Configure email/SMS alert preferences',
    {
      email: z.string().email().optional().describe('Email address for notifications'),
      sms: z.string().optional().describe('Phone number for SMS notifications'),
      worker_offline: z
        .boolean()
        .optional()
        .describe('Alert when a worker goes offline'),
      payout_received: z.boolean().optional().describe('Alert on payout received'),
      hashrate_drop: z.boolean().optional().describe('Alert on hashrate drop'),
      hashrate_drop_threshold: z
        .number()
        .positive()
        .optional()
        .describe('Hashrate drop percentage to trigger alert'),
    },
    async (preferences) => {
      const config: NotificationConfig = preferences;
      const data = await client.put<{ success: boolean }>(ENDPOINTS.NOTIFICATIONS, config);
      return {
        content: [{ type: 'text', text: JSON.stringify(data, null, 2) }],
      };
    },
  );
}
