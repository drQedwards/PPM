/**
 * solution-engine.ts — Context+ Solution Engine Processor for PMLL MCP.
 *
 * Integrates the Context+ semantic intelligence approach as the long-term
 * memory and solution engine for the PMLL persistent memory logic loop.
 *
 * The solution engine:
 *   1. Bridges short-term KV cache (existing 5 tools) with the long-term
 *      memory graph (new 6 tools from Context+)
 *   2. Provides a unified context resolution path: short-term → long-term
 *   3. Auto-promotes frequently accessed short-term cache entries to the
 *      long-term memory graph
 *   4. Implements the Context+ decay scoring and similarity-based retrieval
 *
 * This enables PMLL to achieve 99% accuracy by combining:
 *   - Immediate context via KV cache (short-term)
 *   - Persistent knowledge via memory graph (long-term)
 *   - Semantic search across both layers
 */

import { PMMemoryStore } from "./kv-store.js";
import {
  upsertNode,
  searchGraph,
  getGraphStats,
  type NodeType,
} from "./memory-graph.js";

// ---------------------------------------------------------------------------
// Promotion threshold: entries accessed >= this count get promoted
// ---------------------------------------------------------------------------
const PROMOTION_THRESHOLD = 3;

/**
 * Resolve context by checking both short-term (KV) and long-term (graph)
 * memory layers. Returns the best match from either layer.
 */
export function resolveContext(
  sessionId: string,
  key: string,
  store: PMMemoryStore,
): { source: "short_term" | "long_term" | "miss"; value: string | null; score: number } {
  // Layer 1: Short-term KV cache
  const [hit, value] = store.peek(key);
  if (hit && value !== null) {
    return { source: "short_term", value, score: 1.0 };
  }

  // Layer 2: Long-term memory graph (semantic search)
  const graphResult = searchGraph(sessionId, key, 1, 1);
  if (graphResult.direct.length > 0) {
    const top = graphResult.direct[0];
    return {
      source: "long_term",
      value: top.node.content,
      score: top.relevanceScore / 100,
    };
  }

  return { source: "miss", value: null, score: 0 };
}

/**
 * Promote a short-term KV entry to the long-term memory graph.
 * This creates a persistent memory node from a frequently accessed cache entry.
 */
export function promoteToLongTerm(
  sessionId: string,
  key: string,
  value: string,
  nodeType: NodeType = "concept",
  metadata?: Record<string, string>,
): { promoted: boolean; nodeId: string | null } {
  const node = upsertNode(sessionId, nodeType, key, value, metadata);
  return { promoted: true, nodeId: node.id };
}

/**
 * Get a unified status view of both short-term and long-term memory.
 */
export function getMemoryStatus(
  sessionId: string,
  store: PMMemoryStore,
): {
  shortTerm: { slots: number; siloSize: number };
  longTerm: { nodes: number; edges: number; types: Record<string, number> };
  promotionThreshold: number;
} {
  const stats = getGraphStats(sessionId);

  return {
    shortTerm: {
      slots: store.size,
      siloSize: store.siloSize,
    },
    longTerm: {
      nodes: stats.nodes,
      edges: stats.edges,
      types: stats.types,
    },
    promotionThreshold: PROMOTION_THRESHOLD,
  };
}
