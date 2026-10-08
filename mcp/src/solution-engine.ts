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
 * Designed to improve context retention and retrieval for coding agents by combining:
 *   - Immediate context via KV cache (short-term)
 *   - Long-term knowledge via the memory graph
 *   - Semantic search across both layers
 */

import { PMMemoryStore } from "./kv-store.js";
import {
  findNodeByLabel,
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
 * Semantic fallback in resolveContext must reach this cosine score (0..1).
 * Unrelated keys scored about 0.3-0.35 against small graphs in testing, so a
 * lower bound of 0.5 turns those into misses. Exact label hits score 1.0.
 */
export const MIN_SEMANTIC_SCORE = 0.5;

export interface ResolveContextResult {
  source: "short_term" | "long_term" | "miss";
  value: string | null;
  score: number;
  match: "exact" | "semantic" | null;
  nodeId: string | null;
}

/**
 * Resolve context from both memory layers, in order:
 *   1. short-term KV exact key (score 1, match "exact")
 *   2. long-term node whose label equals `key` exactly (score 1, match "exact")
 *   3. long-term semantic search, only if the top score >= minScore
 *      (default MIN_SEMANTIC_SCORE), match "semantic"
 * Anything else is a miss, so a never-stored key is not answered with an
 * unrelated node.
 */
export function resolveContext(
  sessionId: string,
  key: string,
  store: PMMemoryStore,
  minScore: number = MIN_SEMANTIC_SCORE,
): ResolveContextResult {
  // Layer 1: Short-term KV cache
  const [hit, value] = store.peek(key);
  if (hit && value !== null) {
    return { source: "short_term", value, score: 1.0, match: "exact", nodeId: null };
  }

  // Layer 2: Long-term graph, exact label
  const exact = findNodeByLabel(sessionId, key);
  if (exact) {
    return { source: "long_term", value: exact.content, score: 1.0, match: "exact", nodeId: exact.id };
  }

  // Layer 3: Long-term graph, semantic search above the threshold
  const graphResult = searchGraph(sessionId, key, 1, 1);
  if (graphResult.direct.length > 0) {
    const top = graphResult.direct[0];
    const score = top.relevanceScore / 100;
    if (score >= minScore) {
      return { source: "long_term", value: top.node.content, score, match: "semantic", nodeId: top.node.id };
    }
  }

  return { source: "miss", value: null, score: 0, match: null, nodeId: null };
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
