#!/usr/bin/env node
/**
 * index.ts — MCP server entry point for the Braiins Pool MCP server.
 *
 * Reads configuration from environment variables, creates the API client,
 * registers all MCP tools, and starts the server using the stdio transport
 * (required by the MCP protocol for local tool use).
 *
 * Usage:
 *   BRAIINS_API_KEY=<key> node dist/index.js
 */

import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { BraiinsApiClient } from '../api/client.js';
import { CacheService } from '../utils/cache.js';
import { RateLimiter } from '../utils/ratelimit.js';
import { getLogger } from '../utils/logger.js';
import { getApiKey, getBaseUrl } from './auth.js';
import { registerTools } from './tools.js';

const logger = getLogger('server');

async function main(): Promise<void> {
  const apiKey = getApiKey();
  const baseUrl = getBaseUrl();

  const cache = new CacheService();
  const rateLimiter = new RateLimiter();
  const apiClient = new BraiinsApiClient(apiKey, baseUrl, cache, rateLimiter);

  const server = new McpServer({
    name: 'braiins-pool-mcp-server',
    version: '1.0.0',
  });

  registerTools(server, apiClient);

  const transport = new StdioServerTransport();
  await server.connect(transport);

  logger.info('Braiins Pool MCP server running on stdio');
}

main().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(1);
});
