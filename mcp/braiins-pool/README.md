# Braiins Pool MCP Server

> **Monitor workers, track earnings, and manage your Bitcoin mining operation through natural conversation.**

[![npm](https://img.shields.io/npm/v/@ryno-crypto/braiins-pool-mcp-server)](https://www.npmjs.com/package/@ryno-crypto/braiins-pool-mcp-server)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](../../LICENSE)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.4-blue)](https://www.typescriptlang.org/)

---

## Installation

### Quick Start (NPM)

```bash
# Install globally
npm install -g @ryno-crypto/braiins-pool-mcp-server

# Or install locally in project
npm install @ryno-crypto/braiins-pool-mcp-server
```

### From Source

```bash
# Clone repository
git clone https://github.com/drQedwards/PPM.git
cd PPM/mcp/braiins-pool

# Install dependencies
npm install

# Build TypeScript
npm run build

# Run tests
npm test
```

### Docker Deployment

#### Build Locally

```bash
# Build the Docker image
docker build -t braiins-pool-mcp-server .

# Run the container (MCP uses stdio, not HTTP ports)
docker run --rm -i \
  -e BRAIINS_API_KEY=your_api_key \
  braiins-pool-mcp-server
```

#### Using Docker Compose

Two Docker Compose configurations are available:

| File | Description | Use Case |
|------|-------------|----------|
| `docker-compose.yml` | MCP server only | Standard usage |
| `docker-compose.redis.yml` | MCP server + Redis + Redis Commander | Performance optimization with caching |

**Basic Setup (No Redis)**

```bash
# Set your API key
export BRAIINS_API_KEY=your_api_key

# Start the MCP server
docker compose up -d

# View logs
docker compose logs -f
```

**With Redis Caching**

```bash
# Set your API key
export BRAIINS_API_KEY=your_api_key

# Start MCP server with Redis and Redis Commander
docker compose -f docker-compose.redis.yml up -d

# Access Redis Commander UI
open http://localhost:8081

# View logs
docker compose -f docker-compose.redis.yml logs -f
```

#### Pull from Docker Hub

```bash
# Pull pre-built image
docker pull rynocrypto/braiins-pool-mcp-server:latest

# Run container
docker run --rm -i \
  -e BRAIINS_API_KEY=your_api_key \
  rynocrypto/braiins-pool-mcp-server:latest
```

---

## Configuration

### Environment Variables

Create a `.env` file in your project root (see `.env.example`):

```bash
# Required
BRAIINS_API_KEY=your_api_key_here

# Optional
BRAIINS_API_BASE_URL=https://pool.braiins.com/api/v1
REDIS_URL=redis://localhost:6379
REDIS_ENABLED=true
LOG_LEVEL=info
LOG_FORMAT=pretty
```

### MCP Client Configuration

#### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "braiins-pool": {
      "command": "node",
      "args": ["/path/to/PPM/mcp/braiins-pool/dist/index.js"],
      "env": {
        "BRAIINS_API_KEY": "your_api_key"
      }
    }
  }
}
```

#### Cursor / VS Code

Add to `.cursorrules` or `.vscode/mcp.json`:

```json
{
  "mcp": {
    "servers": {
      "braiins-pool": {
        "command": "npx",
        "args": ["@ryno-crypto/braiins-pool-mcp-server"],
        "env": {
          "BRAIINS_API_KEY": "${env:BRAIINS_API_KEY}"
        }
      }
    }
  }
}
```

### API Key Generation

1. Log in to [Braiins Pool](https://pool.braiins.com)
2. Navigate to **Settings → Access Tokens**
3. Click **Generate New Token**
4. Copy the API token immediately (shown only once)
5. Set as `BRAIINS_API_KEY` environment variable

---

## Available Tools

### Worker Management

| Tool | Description | Parameters | Returns |
|------|-------------|------------|---------|
| `list_workers` | Get all configured workers | `user_id?: string` | `Worker[]` |
| `get_worker_details` | Detailed stats for specific worker | `worker_name: string` | `WorkerDetails` |
| `get_worker_hashrate` | Historical hashrate chart data | `worker_name, start_date, end_date` | `TimeSeries` |
| `restart_worker` | Remote worker restart (if supported) | `worker_name: string` | `boolean` |

### Earnings & Payouts

| Tool | Description | Parameters | Returns |
|------|-------------|------------|---------|
| `get_earnings_summary` | Total unpaid balance + history | `currency?: BTC\|USD` | `EarningsSummary` |
| `get_payout_history` | Past transactions | `limit?: number, offset?: number` | `Payout[]` |
| `estimate_next_payout` | Projected payout time/amount | `current_hashrate: number` | `PayoutEstimate` |

### Pool Statistics

| Tool | Description | Parameters | Returns |
|------|-------------|------------|---------|
| `get_pool_stats` | Network-wide metrics | None | `PoolStats` |
| `get_block_history` | Recent block discoveries | `limit?: number` | `Block[]` |
| `get_network_difficulty` | Current BTC difficulty | None | `number` |

### Configuration

| Tool | Description | Parameters | Returns |
|------|-------------|------------|---------|
| `update_payout_threshold` | Minimum payout amount | `threshold: number, currency: string` | `boolean` |
| `set_notification_preferences` | Email/SMS alerts | `preferences: NotificationConfig` | `boolean` |

---

## Architecture

```
┌─────────────────┐
│  MCP Client     │  (Claude, Cursor, VS Code)
│  (AI Assistant) │
└────────┬────────┘
         │ MCP Protocol (JSON-RPC 2.0)
         │
┌────────▼────────┐
│  MCP Server     │
│  - Tool Router  │  ← Validates requests
│  - Auth Manager │  ← Handles API keys
│  - Cache Layer  │  ← Redis/in-memory
└────────┬────────┘
         │ HTTPS
         │
┌────────▼────────┐
│ Braiins Pool    │
│ REST API        │
└─────────────────┘
```

### Component Breakdown

**Server Core (`src/server/`)**
- `index.ts`: MCP protocol implementation and entry point
- `tools.ts`: Tool definitions and handlers
- `auth.ts`: API authentication logic

**API Client (`src/api/`)**
- `client.ts`: HTTP request wrapper with caching and rate limiting
- `endpoints.ts`: Braiins API endpoint mappings
- `types.ts`: TypeScript interfaces

**Utilities (`src/utils/`)**
- `cache.ts`: Response caching (in-memory or Redis)
- `ratelimit.ts`: Request throttling (token bucket)
- `logger.ts`: Structured logging (Winston)

---

## Development

### Setup Development Environment

```bash
cd mcp/braiins-pool

# Install dependencies
npm install

# Copy environment template
cp .env.example .env
# Edit .env and set your BRAIINS_API_KEY

# Start development server with hot reload
npm run dev
```

### Project Scripts

```bash
npm run build      # Compile TypeScript → JavaScript
npm run dev        # Watch mode with auto-reload
npm test           # Run test suite
npm run test:watch # Continuous testing
npm run lint       # ESLint checks
npm run typecheck  # TypeScript validation
```

---

## Companion Servers

| Server | Directory | Description |
|--------|-----------|-------------|
| **PMLL Memory MCP** | [`../pmll_memory_mcp/`](../pmll_memory_mcp/) | Short-term KV context memory and Q-promise deduplication |
| **Unstoppable Domains** | [`../unstoppable-domains/`](../unstoppable-domains/) | Search, purchase, and manage Web3 domain names |

Use the PMLL Memory MCP alongside this server to cache Braiins API responses and eliminate redundant network calls across agent subtasks.
