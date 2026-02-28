/**
 * auth.ts — API authentication logic for the Braiins Pool MCP server.
 *
 * Reads the API key from the environment and validates that it is present
 * before the server starts handling requests.
 */

import { getLogger } from '../utils/logger.js';

const logger = getLogger('auth');

export function getApiKey(): string {
  const key = process.env['BRAIINS_API_KEY'];
  if (!key) {
    logger.error(
      'BRAIINS_API_KEY environment variable is not set. ' +
        'Generate a token at https://pool.braiins.com → Settings → Access Tokens.',
    );
    process.exit(1);
  }
  return key;
}

export function getBaseUrl(): string {
  return process.env['BRAIINS_API_BASE_URL'] ?? 'https://pool.braiins.com/api/v1';
}
