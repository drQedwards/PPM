/**
 * logger.ts — Structured logging utility using Winston.
 *
 * Supports two output formats:
 *   pretty — human-readable coloured output (development default)
 *   json   — machine-parseable single-line JSON (production / Docker)
 *
 * Log level and format are driven by environment variables:
 *   LOG_LEVEL  — error | warn | info | debug  (default: info)
 *   LOG_FORMAT — pretty | json                (default: pretty)
 */

import winston from 'winston';

const { combine, timestamp, colorize, printf, json, errors } = winston.format;

const LOG_LEVEL = process.env['LOG_LEVEL'] ?? 'info';
const LOG_FORMAT = process.env['LOG_FORMAT'] ?? 'pretty';

const prettyFormat = combine(
  colorize({ all: true }),
  timestamp({ format: 'HH:mm:ss' }),
  errors({ stack: true }),
  printf(({ level, message, timestamp: ts, stack, ...meta }) => {
    const metaStr = Object.keys(meta).length ? ` ${JSON.stringify(meta)}` : '';
    return `${ts} [${level}] ${message}${stack ? `\n${stack}` : ''}${metaStr}`;
  }),
);

const jsonFormat = combine(timestamp(), errors({ stack: true }), json());

const rootLogger = winston.createLogger({
  level: LOG_LEVEL,
  format: LOG_FORMAT === 'json' ? jsonFormat : prettyFormat,
  transports: [new winston.transports.Console()],
});

export function getLogger(component: string): winston.Logger {
  return rootLogger.child({ component });
}

export default rootLogger;
