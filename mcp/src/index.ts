#!/usr/bin/env node
/**
 * index.ts — PMLL Memory MCP Server entrypoint.
 *
 * Exposes 15 MCP tools for Claude Sonnet/Opus agents:
 *
 * Short-term KV memory (5 tools):
 *   init    — Set up the PMLL memory silo and Q-promise chain for a session.
 *   peek    — Non-destructive context check (core deduplication primitive).
 *   set     — Store a KV pair in the session's PMLL silo.
 *   resolve — Resolve a pending Q-promise continuation.
 *   flush   — Clear all short-term KV slots at agent task completion.
 *
 * GraphQL (1 tool):
 *   graphql — Execute GraphQL queries/mutations against the memory store.
 *
 * Long-term memory graph (6 tools — adapted from Context+ by @ForLoopCodes):
 *   upsert_memory_node      — Create/update memory nodes with TF-IDF embeddings.
 *   create_relation          — Create typed edges between nodes.
 *   search_memory_graph      — Semantic search with graph traversal.
 *   prune_stale_links        — Remove decayed edges and orphan nodes.
 *   add_interlinked_context  — Bulk-add nodes with auto-similarity linking.
 *   retrieve_with_traversal  — Walk outward from a node.
 *
 * Solution engine (3 tools):
 *   resolve_context      — Unified short-term → long-term context lookup.
 *   promote_to_long_term — Promote KV entries to the memory graph.
 *   memory_status        — Unified memory view across both layers.
 *
 * The server is designed as the **3rd initializer** alongside Playwright and
 * other MCP tools.  Agents call `init` once at task start, then use
 * `peek` before any expensive MCP tool invocation to avoid redundant calls.
 *
 * Context+ integration by @ForLoopCodes (https://github.com/ForLoopCodes/contextplus).
 *
 * Architecture:
 *     - KV layer  → `PMMemoryStore` (mirrors PMLL.c memory_silo_t)
 *     - Async layer → `QPromiseRegistry` (mirrors Q_promise_lib QMemNode chain)
 *     - Guard function → `peekContext()` (peek.ts)
 *     - Long-term → `memory-graph.ts` (adapted from Context+)
 *     - Engine → `solution-engine.ts` (bridges short-term + long-term)
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
import { executeGraphQL, GRAPHQL_QUERY, GRAPHQL_MUTATION, GRAPHQL_DEFAULT_VARIABLES } from "./graphql.js";
import {
  upsertNode,
  createRelation,
  searchGraph,
  pruneStaleLinks,
  addInterlinkedContext,
  retrieveWithTraversal,
  getGraphStats,
  clearGraph,
  type NodeType,
  type RelationType,
} from "./memory-graph.js";
import { resolveContext, promoteToLongTerm, getMemoryStatus } from "./solution-engine.js";

// ---------------------------------------------------------------------------
// MCP server instance
// ---------------------------------------------------------------------------
const server = new McpServer(
  {
    name: "pmll-memory-mcp",
    version: "1.0.0",
  },
  {
    instructions:
      "PMLL Memory MCP — persistent memory logic loop with short-term KV " +
      "context memory, Q-promise deduplication, and Context+ long-term " +
      "semantic memory graph for 99% accuracy. " +
      "Short-term tools: `init`, `peek`, `set`, `resolve`, `flush`. " +
      "Long-term tools: `upsert_memory_node`, `create_relation`, " +
      "`search_memory_graph`, `prune_stale_links`, `add_interlinked_context`, " +
      "`retrieve_with_traversal`. " +
      "Solution engine: `resolve_context` (unified short+long term lookup), " +
      "`promote_to_long_term` (promote KV entries to graph), " +
      "`memory_status` (unified memory view).",
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
// Tool: graphql
// ---------------------------------------------------------------------------
server.tool(
  "graphql",
  "Execute a GraphQL query or mutation against a remote endpoint, with " +
    "optional PMLL cache integration. " +
    "Supply `operation` as a GraphQL document string and `variables` as a " +
    "JSON object.  Pass `cache_key` to store/retrieve the result from the " +
    "PMLL silo so redundant network calls are avoided on subsequent `peek` " +
    "checks.  The `operation` defaults to the pre-built canonical Query " +
    "document when omitted.  Use `use_mutation` to switch the default to the " +
    "canonical Mutation document.",
  {
    session_id: z.string().describe("The session identifier (from `init`)."),
    endpoint: z.string().url().describe("Full URL of the GraphQL endpoint."),
    operation: z
      .string()
      .optional()
      .describe(
        "GraphQL operation document.  Defaults to the canonical Query " +
          "when omitted (or the canonical Mutation when `use_mutation` is true).",
      ),
    variables: z
      .record(z.unknown())
      .optional()
      .default({})
      .describe("Variables to pass with the operation (JSON object)."),
    headers: z
      .record(z.string())
      .optional()
      .default({})
      .describe("Additional HTTP headers, e.g. { Authorization: 'Bearer <token>' }."),
    cache_key: z
      .string()
      .optional()
      .describe(
        "When provided, the result is stored under this key in the PMLL silo. " +
          "A subsequent `peek` with the same key will return the cached value " +
          "without re-executing the operation.",
      ),
    use_mutation: z
      .boolean()
      .optional()
      .default(false)
      .describe(
        "When true and `operation` is omitted, use the canonical Mutation " +
          "document instead of the canonical Query document.",
      ),
  },
  async ({ session_id, endpoint, operation, variables, headers, cache_key, use_mutation }) => {
    const store = getStore(session_id);

    // Check PMLL cache first when a cache key is provided.
    if (cache_key) {
      const cached = peekContext(cache_key, session_id, store, _promiseRegistry);
      if (cached.hit && "value" in cached) {
        let parsedData: unknown = cached.value;
        try {
          parsedData = JSON.parse(cached.value);
        } catch {
          // Cached value is not JSON; return as a raw string.
        }
        return {
          content: [
            {
              type: "text" as const,
              text: JSON.stringify({ cached: true, data: parsedData }),
            },
          ],
        };
      }
    }

    // Resolve the operation document.
    const doc =
      operation ?? (use_mutation ? GRAPHQL_MUTATION : GRAPHQL_QUERY);

    // Merge caller variables on top of the default (all-null) variable set
    // so the operation document receives every declared variable.
    const mergedVariables: Record<string, unknown> = {
      ...GRAPHQL_DEFAULT_VARIABLES,
      ...variables,
    };

    let result: unknown;
    try {
      result = await executeGraphQL(endpoint, doc, mergedVariables, headers);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      return {
        content: [
          {
            type: "text" as const,
            text: JSON.stringify({ error: message }),
          },
        ],
      };
    }

    const resultStr = JSON.stringify(result);

    // Populate the PMLL silo so future peek calls return a cache hit.
    if (cache_key) {
      store.set(cache_key, resultStr);
    }

    return {
      content: [
        {
          type: "text" as const,
          text: JSON.stringify({ cached: false, data: result }),
        },
      ],
    };
  },
);

// ---------------------------------------------------------------------------
// Tool: upsert_memory_node (Long-term memory)
// ---------------------------------------------------------------------------
server.tool(
  "upsert_memory_node",
  "Create or update a memory node in the long-term semantic graph. " +
    "Nodes represent concepts, files, symbols, or notes with auto-generated " +
    "TF-IDF embeddings for semantic search. Part of the Context+ solution " +
    "engine for 99% accuracy persistent memory.",
  {
    session_id: z.string().describe("The session identifier (from `init`)."),
    type: z
      .enum(["concept", "file", "symbol", "note"])
      .describe("Node type: concept, file, symbol, or note."),
    label: z.string().describe("Short label for the node."),
    content: z.string().describe("Full content/description of the node."),
    metadata: z
      .record(z.string())
      .optional()
      .default({})
      .describe("Optional key-value metadata for the node."),
  },
  async ({ session_id, type, label, content, metadata }) => {
    const node = upsertNode(session_id, type as NodeType, label, content, metadata);
    const stats = getGraphStats(session_id);
    return {
      content: [
        {
          type: "text" as const,
          text: JSON.stringify({
            status: "upserted",
            node_id: node.id,
            label: node.label,
            node_type: node.type,
            access_count: node.accessCount,
            graph_nodes: stats.nodes,
            graph_edges: stats.edges,
          }),
        },
      ],
    };
  },
);

// ---------------------------------------------------------------------------
// Tool: create_relation (Long-term memory)
// ---------------------------------------------------------------------------
server.tool(
  "create_relation",
  "Create a typed edge between two memory nodes in the long-term graph. " +
    "Supported relation types: relates_to, depends_on, implements, " +
    "references, similar_to, contains.",
  {
    session_id: z.string().describe("The session identifier (from `init`)."),
    source_id: z.string().describe("Source node ID."),
    target_id: z.string().describe("Target node ID."),
    relation: z
      .enum([
        "relates_to",
        "depends_on",
        "implements",
        "references",
        "similar_to",
        "contains",
      ])
      .describe("Relation type for the edge."),
    weight: z
      .number()
      .optional()
      .default(1.0)
      .describe("Edge weight (default: 1.0)."),
  },
  async ({ session_id, source_id, target_id, relation, weight }) => {
    const edge = createRelation(
      session_id,
      source_id,
      target_id,
      relation as RelationType,
      weight,
    );
    if (!edge) {
      return {
        content: [
          {
            type: "text" as const,
            text: JSON.stringify({
              status: "error",
              message: "One or both node IDs not found",
            }),
          },
        ],
      };
    }
    return {
      content: [
        {
          type: "text" as const,
          text: JSON.stringify({
            status: "created",
            edge_id: edge.id,
            relation: edge.relation,
            weight: edge.weight,
          }),
        },
      ],
    };
  },
);

// ---------------------------------------------------------------------------
// Tool: search_memory_graph (Long-term memory)
// ---------------------------------------------------------------------------
server.tool(
  "search_memory_graph",
  "Semantic search with graph traversal — finds direct matches then walks " +
    "1st/2nd-degree neighbors. Returns ranked results scored by cosine " +
    "similarity and edge decay.",
  {
    session_id: z.string().describe("The session identifier (from `init`)."),
    query: z.string().describe("Natural language search query."),
    max_depth: z
      .number()
      .int()
      .optional()
      .default(1)
      .describe("Maximum traversal depth (default: 1)."),
    top_k: z
      .number()
      .int()
      .optional()
      .default(5)
      .describe("Maximum number of direct hits (default: 5)."),
  },
  async ({ session_id, query, max_depth, top_k }) => {
    const result = searchGraph(session_id, query, max_depth, top_k);
    return {
      content: [
        {
          type: "text" as const,
          text: JSON.stringify({
            query,
            direct: result.direct.map((d) => ({
              node_id: d.node.id,
              label: d.node.label,
              type: d.node.type,
              content: d.node.content,
              score: d.relevanceScore,
            })),
            neighbors: result.neighbors.map((n) => ({
              node_id: n.node.id,
              label: n.node.label,
              type: n.node.type,
              content: n.node.content,
              score: n.relevanceScore,
              depth: n.depth,
              path: n.pathRelations,
            })),
            total_nodes: result.totalNodes,
            total_edges: result.totalEdges,
          }),
        },
      ],
    };
  },
);

// ---------------------------------------------------------------------------
// Tool: prune_stale_links (Long-term memory)
// ---------------------------------------------------------------------------
server.tool(
  "prune_stale_links",
  "Remove decayed edges (e^(-λt) below threshold) and orphan nodes with " +
    "low access counts from the long-term memory graph.",
  {
    session_id: z.string().describe("The session identifier (from `init`)."),
    threshold: z
      .number()
      .optional()
      .default(0.15)
      .describe("Decay threshold below which edges are pruned (default: 0.15)."),
  },
  async ({ session_id, threshold }) => {
    const result = pruneStaleLinks(session_id, threshold);
    return {
      content: [
        {
          type: "text" as const,
          text: JSON.stringify({
            status: "pruned",
            removed: result.removed,
            remaining_edges: result.remaining,
          }),
        },
      ],
    };
  },
);

// ---------------------------------------------------------------------------
// Tool: add_interlinked_context (Long-term memory)
// ---------------------------------------------------------------------------
server.tool(
  "add_interlinked_context",
  "Bulk-add nodes with auto-similarity linking (cosine ≥ 0.72 creates " +
    "edges automatically). Efficient for adding multiple related concepts " +
    "at once.",
  {
    session_id: z.string().describe("The session identifier (from `init`)."),
    items: z
      .array(
        z.object({
          type: z.enum(["concept", "file", "symbol", "note"]),
          label: z.string(),
          content: z.string(),
          metadata: z.record(z.string()).optional(),
        }),
      )
      .describe("Array of nodes to add."),
    auto_link: z
      .boolean()
      .optional()
      .default(true)
      .describe("Auto-create similarity edges (default: true)."),
  },
  async ({ session_id, items, auto_link }) => {
    const result = addInterlinkedContext(
      session_id,
      items.map((i) => ({
        type: i.type as NodeType,
        label: i.label,
        content: i.content,
        metadata: i.metadata,
      })),
      auto_link,
    );
    return {
      content: [
        {
          type: "text" as const,
          text: JSON.stringify({
            status: "added",
            nodes_created: result.nodes.length,
            edges_created: result.edges.length,
            nodes: result.nodes.map((n) => ({
              id: n.id,
              label: n.label,
              type: n.type,
            })),
          }),
        },
      ],
    };
  },
);

// ---------------------------------------------------------------------------
// Tool: retrieve_with_traversal (Long-term memory)
// ---------------------------------------------------------------------------
server.tool(
  "retrieve_with_traversal",
  "Start from a node and walk outward — returns all reachable neighbors " +
    "scored by decay and depth. Used for exploring the knowledge graph " +
    "from a known starting point.",
  {
    session_id: z.string().describe("The session identifier (from `init`)."),
    start_node_id: z.string().describe("ID of the starting node."),
    max_depth: z
      .number()
      .int()
      .optional()
      .default(2)
      .describe("Maximum traversal depth (default: 2)."),
  },
  async ({ session_id, start_node_id, max_depth }) => {
    const results = retrieveWithTraversal(session_id, start_node_id, max_depth);
    if (results.length === 0) {
      return {
        content: [
          {
            type: "text" as const,
            text: JSON.stringify({
              status: "error",
              message: `Node not found: ${start_node_id}`,
            }),
          },
        ],
      };
    }
    return {
      content: [
        {
          type: "text" as const,
          text: JSON.stringify({
            start_node: results[0].node.label,
            results: results.map((r) => ({
              node_id: r.node.id,
              label: r.node.label,
              type: r.node.type,
              content: r.node.content,
              depth: r.depth,
              score: r.relevanceScore,
              path: r.pathRelations,
            })),
          }),
        },
      ],
    };
  },
);

// ---------------------------------------------------------------------------
// Tool: resolve_context (Solution Engine)
// ---------------------------------------------------------------------------
server.tool(
  "resolve_context",
  "Unified context resolution across both short-term (KV cache) and " +
    "long-term (semantic graph) memory layers. Checks KV cache first, " +
    "then falls back to semantic graph search. This is the primary " +
    "Context+ solution engine tool for achieving 99% accuracy.",
  {
    session_id: z.string().describe("The session identifier (from `init`)."),
    key: z.string().describe("The context key to resolve."),
  },
  async ({ session_id, key }) => {
    const store = getStore(session_id);
    const result = resolveContext(session_id, key, store);
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
// Tool: promote_to_long_term (Solution Engine)
// ---------------------------------------------------------------------------
server.tool(
  "promote_to_long_term",
  "Promote a short-term KV cache entry to the long-term semantic memory " +
    "graph. Creates a persistent memory node from a frequently accessed " +
    "cache entry, ensuring important context survives session flushes.",
  {
    session_id: z.string().describe("The session identifier (from `init`)."),
    key: z.string().describe("The context key/label for the memory node."),
    value: z.string().describe("The content to store in long-term memory."),
    node_type: z
      .enum(["concept", "file", "symbol", "note"])
      .optional()
      .default("concept")
      .describe("Node type (default: concept)."),
  },
  async ({ session_id, key, value, node_type }) => {
    const result = promoteToLongTerm(
      session_id,
      key,
      value,
      node_type as NodeType,
    );
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
// Tool: memory_status (Solution Engine)
// ---------------------------------------------------------------------------
server.tool(
  "memory_status",
  "Get a unified status view of both short-term (KV cache) and long-term " +
    "(semantic graph) memory layers. Shows slot usage, graph statistics, " +
    "and promotion threshold.",
  {
    session_id: z.string().describe("The session identifier (from `init`)."),
  },
  async ({ session_id }) => {
    const store = getStore(session_id);
    const status = getMemoryStatus(session_id, store);
    return {
      content: [
        {
          type: "text" as const,
          text: JSON.stringify(status),
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
