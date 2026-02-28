# Unstoppable Domains MCP Server

> **Search, purchase, and manage Web3 domain names through natural conversation.**

[![MCP Server](https://img.shields.io/badge/MCP-Remote%20Server-blue)](https://api.unstoppabledomains.com/mcp/v1)
[![License](https://img.shields.io/badge/License-Proprietary-red)](https://unstoppabledomains.com/terms)

---

## What it does

The **Unstoppable Domains MCP server** is a hosted [Model Context Protocol](https://modelcontextprotocol.io) server that lets AI assistants (Claude, ChatGPT, and automated agents) search, purchase, and fully manage Web3 domain names through natural conversation.

**MCP Server URL:**
```
https://api.unstoppabledomains.com/mcp/v1
```

---

## What Can You Do?

With the MCP server, you can ask AI assistants to:

- **Search & Purchase Domains** — Find available domains, check pricing, and complete purchases
- **Manage Your Portfolio** — View your domains, filter by status, track expirations
- **Configure DNS** — Set up A, CNAME, MX, TXT, and other DNS records
- **Sell on Marketplace** — List domains for sale, manage offers, negotiate with buyers
- **Communicate** — Contact domain sellers and manage conversations

---

## Quick Start

Point your AI tool at the MCP server URL:

```
https://api.unstoppabledomains.com/mcp/v1
```

When prompted, authenticate with your Unstoppable Domains account via OAuth. Then start chatting to manage your domains.

---

## Setup Instructions

### ChatGPT

#### Option 1: Use the Custom GPT (Easiest)

Open the pre-built **[Unstoppable Domains GPT](https://chatgpt.com/g/g-698a7d3768448191a7177d7f3f22a130-unstoppable-domains)** and start chatting immediately.

> The custom GPT supports core domain management tasks. For the full toolset — including responding to offers and managing marketplace conversations — use the MCP server connection below.

#### Option 2: Add the MCP Server to ChatGPT

Requires ChatGPT Plus, Pro, Team, or Enterprise. Complete these steps in the [ChatGPT web app](https://chatgpt.com).

1. Open [ChatGPT's connector settings](https://chatgpt.com/#settings/Connectors/Advanced) and enable **"Developer Mode (beta)"** under Advanced Settings.
2. Navigate to the main Connectors page and click **"Create"**.
3. Paste the MCP server URL:
   ```
   https://api.unstoppabledomains.com/mcp/v1
   ```
4. Leave authentication as the default setting and click **Save**.
5. Start a new conversation and ask ChatGPT to search for a domain. Authorize the connection when prompted.

---

### Claude (Desktop & Web)

Setup is the same for both Claude Desktop and [claude.ai](https://claude.ai).

#### Paid Plans (Pro, Max, Team, Enterprise)

1. Open **Settings** → **Connectors**
2. Click **"Add custom connector"**
3. Enter the MCP server URL:
   ```
   https://api.unstoppabledomains.com/mcp/v1
   ```
4. Click **"Add"** and sign in with your Unstoppable Domains account when prompted.
5. In any conversation, click the **"+"** button in the compose area, select **"Connectors"**, and toggle on Unstoppable Domains.

#### Free Plans (Claude Desktop only)

Free users can connect via the JSON configuration file. This project ships a ready-made example at [`claude_desktop_config.json`](./claude_desktop_config.json) that combines this server with the [PMLL Memory MCP](../README.md) server.

1. Open Claude Desktop → **Claude** (menu bar) → **Settings** → **Developer** → **Edit Config**

   Config file location:
   - **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

2. Add (or merge) the following into your config:
   ```json
   {
     "mcpServers": {
       "unstoppable-domains": {
         "command": "npx",
         "args": ["mcp-remote", "https://api.unstoppabledomains.com/mcp/v1"]
       }
     }
   }
   ```

3. Save and **restart Claude Desktop** completely.
4. After restarting, look for the **hammer icon** in the bottom-right corner of the chat input to verify the tools are available.

> **Note:** Requires [Node.js](https://nodejs.org/) installed on your machine. Uses [mcp-remote](https://www.npmjs.com/package/mcp-remote) to bridge the remote MCP server to Claude's local stdio transport.

---

### Claude Code

Add the MCP server with a single command:

```bash
claude mcp add --transport http unstoppable-domains https://api.unstoppabledomains.com/mcp/v1
```

Then authenticate inside Claude Code:

1. Start a Claude Code session
2. Run `/mcp` to check the server status
3. Follow the browser-based OAuth flow to sign in with your Unstoppable Domains account
4. Once authenticated, all Unstoppable Domains tools are available in your session

To make the server available across all projects (not just the current one):

```bash
claude mcp add --transport http --scope user unstoppable-domains https://api.unstoppabledomains.com/mcp/v1
```

---

## Combined Config with PMLL Memory MCP

When using both servers together (recommended for agent tasks), use the combined config in [`claude_desktop_config.json`](./claude_desktop_config.json):

```json
{
  "mcpServers": {
    "pmll-memory-mcp": {
      "command": "uvx",
      "args": ["pmll-memory-mcp"]
    },
    "unstoppable-domains": {
      "command": "npx",
      "args": ["mcp-remote", "https://api.unstoppabledomains.com/mcp/v1"]
    }
  }
}
```

The PMLL Memory MCP acts as the **3rd initializer**, caching results from Unstoppable Domains API calls so repeated queries don't trigger redundant network requests. See the [PMLL Memory MCP README](../README.md) for the `peek()` pattern.

---

## Authentication

### OAuth 2.0 (Recommended)

OAuth provides scoped, browser-based authentication tied to your Unstoppable Domains account.

**Available scopes:**

| Scope | Access |
| --- | --- |
| `domains:search` | Search domains, check availability |
| `portfolio:read` | View your domains, DNS records, offers |
| `portfolio:write` | Manage DNS, create listings, send messages |
| `cart:read` | View cart and payment methods |
| `cart:write` | Add/remove cart items |
| `checkout` | Complete purchases |

To revoke access, go to [Account Settings](https://unstoppabledomains.com/account/settings?tab=advanced).

### API Key (Advanced)

For manual configuration or custom integrations:

1. Go to [Account Settings](https://unstoppabledomains.com/account/settings?tab=advanced) → **Advanced**
2. Find the **MCP API Key** section and generate a key (format: `ud_mcp_*`)
3. Use the key as a Bearer token:
   ```
   Authorization: Bearer ud_mcp_your_key_here
   ```

**Security tip:** Store your API key in an environment variable:

```bash
export UD_MCP_API_KEY="ud_mcp_your_key_here"
```

API keys grant full access to all tools. Use OAuth for scoped access.

---

## API Reference

| Item | Value |
| --- | --- |
| Endpoint | `https://api.unstoppabledomains.com/mcp/v1/` |
| OpenAPI Spec | `https://api.unstoppabledomains.com/mcp/v1/openapi.json` |
| Authentication | `Authorization: Bearer <token>` |
| Protocol | MCP (Model Context Protocol) over HTTP |

For the full interactive API reference, see the [MCP API Reference](https://unstoppabledomains.com/apis/mcp/openapi).
