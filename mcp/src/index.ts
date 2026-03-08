#!/usr/bin/env node
/**
 * index.ts — PMLL Memory MCP Server entrypoint.
 *
 * Exposes five MCP tools for Claude Sonnet/Opus agents:
 *
 *   init    — Set up the PMLL memory silo and Q-promise chain for a session.
 *   peek    — Non-destructive context check (core deduplication primitive).
 *   set     — Store a KV pair in the session's PMLL silo.
 *   resolve — Resolve a pending Q-promise continuation.
 *   flush   — Clear all short-term KV slots at agent task completion.
 *
 * The server is designed as the **3rd initializer** alongside Playwright and
 * other MCP tools.  Agents call `init` once at task start, then use
 * `peek` before any expensive MCP tool invocation to avoid redundant calls.
 *
 * Architecture:
 *     - KV layer  → `PMMemoryStore` (mirrors PMLL.c memory_silo_t)
 *     - Async layer → `QPromiseRegistry` (mirrors Q_promise_lib QMemNode chain)
 *     - Guard function → `peekContext()` (peek.ts)
 *
 * Usage:
 *     npx pmll-memory-mcp                        # stdio transport
 *     node dist/index.js                         # via compiled output
 *
 * License: MIT
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

import { getStore, dropStore } from "./kv-store.js";
import { QPromiseRegistry } from "./q-promise-bridge.js";
import { peekContext } from "./peek.js";

// ---------------------------------------------------------------------------
// MCP server instance
// ---------------------------------------------------------------------------
const server = new McpServer(
  {
    name: "pmll-memory-mcp",
    version: "0.1.0",
  },
  {
    instructions:
      "PMLL Memory MCP — short-term KV context memory and Q-promise " +
      "deduplication for Claude agent tasks. " +
      "Call `init` once at task start, `peek` before every expensive " +
      "MCP tool to check the cache, `set` to populate it, `resolve` to " +
      "finalise async promises, and `flush` at task completion.",
  },
);

// Module-level Q-promise registry shared across all sessions.
// Mirrors the global QMemNode chain pool in Q_promise_lib.
export const _promiseRegistry = new QPromiseRegistry();

// Track which sessions have been initialised (sessionId → siloSize).
export const _activeSessions: Map<string, number> = new Map();

// ---------------------------------------------------------------------------
// Tool: init
// ---------------------------------------------------------------------------
server.tool(
  "init",
  "Initialise the PMLL memory silo for an agent session. " +
    "Call this once at the start of every agent task, as the 3rd " +
    "initializer alongside Playwright.  Sets up the KV silo and prepares " +
    "the Q-promise chain for the session.",
  {
    session_id: z.string().describe("Unique identifier for this agent task (e.g. a UUID)."),
    silo_size: z
      .number()
      .int()
      .positive()
      .default(256)
      .describe("Maximum number of KV slots (mirrors memory_silo_t.size)."),
  },
  async ({ session_id, silo_size }) => {
    // Lazily create the store; also resets an existing session's silo.
    const store = getStore(session_id, silo_size);
    store.siloSize = silo_size;
    _activeSessions.set(session_id, silo_size);

    return {
      content: [
        {
          type: "text" as const,
          text: JSON.stringify({
            status: "initialized",
            session_id,
            silo_size,
          }),
        },
      ],
    };
  },
);

// ---------------------------------------------------------------------------
// Tool: peek
// ---------------------------------------------------------------------------
server.tool(
  "peek",
  "Non-destructive context check — the core deduplication primitive. " +
    "Call this before any Playwright or other MCP tool invocation to " +
    "check whether the required context already exists in the PMLL silo or " +
    "is in-flight as a Q-promise.",
  {
    session_id: z.string().describe("The session identifier (from `init`)."),
    key: z.string().describe("The context key to look up."),
  },
  async ({ session_id, key }) => {
    const store = getStore(session_id);
    const result = peekContext(key, session_id, store, _promiseRegistry);

    return {
      content: [
        {
          type: "text" as const,
          text: JSON.stringify(result),
        },
      ],
    };
  },
);

// ---------------------------------------------------------------------------
// Tool: set
// ---------------------------------------------------------------------------
server.tool(
  "set",
  "Store a KV pair in the session's PMLL memory silo. " +
    "Call after a successful (non-cached) MCP tool invocation to populate " +
    "the silo so future `peek` calls return a cache hit. " +
    "Mirrors PMLL.c::update_silo() writing a var/value pair into the silo.",
  {
    session_id: z.string().describe("The session identifier (from `init`)."),
    key: z.string().describe("The context key."),
    value: z.string().describe("The string value to cache."),
  },
  async ({ session_id, key, value }) => {
    const store = getStore(session_id);
    const index = store.set(key, value);

    return {
      content: [
        {
          type: "text" as const,
          text: JSON.stringify({ status: "stored", index }),
        },
      ],
    };
  },
);

// ---------------------------------------------------------------------------
// Tool: resolve
// ---------------------------------------------------------------------------
server.tool(
  "resolve",
  "Check or resolve a Q-promise continuation. " +
    "Mirrors the `QThenCallback` mechanism in Q_promise_lib/Q_promises.h — " +
    "the callback is invoked when a QMemNode's payload becomes available. " +
    "If the promise is already resolved, returns its payload immediately. " +
    "If still pending, returns `{status: \"pending\", payload: null}`.",
  {
    session_id: z
      .string()
      .describe("The session identifier (for context; not used to namespace promises)."),
    promise_id: z.string().describe("The promise identifier previously registered."),
  },
  async ({ session_id: _sessionId, promise_id }) => {
    const [found, status, payload] = _promiseRegistry.peekPromise(promise_id);

    let result: { status: string; payload: string | null };
    if (!found) {
      result = { status: "pending", payload: null };
    } else {
      result = { status: status!, payload };
    }

    return {
      content: [
        {
          type: "text" as const,
          text: JSON.stringify(result),
        },
      ],
    };
  },
);

// ---------------------------------------------------------------------------
// Tool: flush
// ---------------------------------------------------------------------------
server.tool(
  "flush",
  "Clear all short-term KV slots for a session. " +
    "Call at agent task completion to free memory.  Mirrors the teardown " +
    "of a memory_silo_t allocation (PMLL.c::free_pml).",
  {
    session_id: z.string().describe("The session identifier (from `init`)."),
  },
  async ({ session_id }) => {
    const cleared = dropStore(session_id);
    _activeSessions.delete(session_id);

    return {
      content: [
        {
          type: "text" as const,
          text: JSON.stringify({ status: "flushed", cleared_count: cleared }),
        },
      ],
    };
  },
);

// ---------------------------------------------------------------------------
// Entry-point
// ---------------------------------------------------------------------------

/** Run the MCP server over stdio (default transport). */
async function main(): Promise<void> {
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

main().catch((error: unknown) => {
  console.error("Fatal error in MCP server:", error);
  process.exit(1);
});

export { server };
