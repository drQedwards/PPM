/**
 * memory-graph.ts — In-memory property graph for long-term context memory.
 *
 * Adapted from Context+ (github.com/drQedwards/contextplus) memory-graph.ts.
 * Provides a persistent memory graph with typed nodes, weighted edges, decay
 * scoring, and graph traversal for the PMLL MCP solution engine.
 *
 * Architecture:
 *   - Nodes: concept, file, symbol, note — each with TF-IDF embeddings
 *   - Edges: typed relations with temporal decay (e^(-λt))
 *   - Search: cosine similarity + graph neighbor traversal
 *   - Persistence: JSON serialization to session-level storage
 *
 * The graph serves as the long-term memory layer complementing the existing
 * short-term KV store (init/peek/set/resolve/flush tools).
 */

import { embed, cosineSimilarity } from "./embeddings.js";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type NodeType = "concept" | "file" | "symbol" | "note";

export type RelationType =
  | "relates_to"
  | "depends_on"
  | "implements"
  | "references"
  | "similar_to"
  | "contains";

export interface MemoryNode {
  id: string;
  type: NodeType;
  label: string;
  content: string;
  embedding: number[];
  createdAt: number;
  lastAccessed: number;
  accessCount: number;
  metadata: Record<string, string>;
}

export interface MemoryEdge {
  id: string;
  source: string;
  target: string;
  relation: RelationType;
  weight: number;
  createdAt: number;
  metadata: Record<string, string>;
}

export interface TraversalResult {
  node: MemoryNode;
  depth: number;
  pathRelations: string[];
  relevanceScore: number;
}

export interface GraphSearchResult {
  direct: TraversalResult[];
  neighbors: TraversalResult[];
  totalNodes: number;
  totalEdges: number;
}

interface GraphStore {
  nodes: Record<string, MemoryNode>;
  edges: Record<string, MemoryEdge>;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DECAY_LAMBDA = 0.05;
const SIMILARITY_THRESHOLD = 0.72;
const STALE_THRESHOLD = 0.15;

// ---------------------------------------------------------------------------
// Graph registry (session-scoped)
// ---------------------------------------------------------------------------

const _graphStores: Map<string, GraphStore> = new Map();

/** Exposed for testing: direct access to graph store registry. */
export const _graphStoresMap = _graphStores;

function generateId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function getGraph(sessionId: string): GraphStore {
  let store = _graphStores.get(sessionId);
  if (!store) {
    store = { nodes: {}, edges: {} };
    _graphStores.set(sessionId, store);
  }
  return store;
}

function decayWeight(edge: MemoryEdge): number {
  const daysSinceCreation = (Date.now() - edge.createdAt) / 86_400_000;
  return edge.weight * Math.exp(-DECAY_LAMBDA * daysSinceCreation);
}

function getEdgesForNode(graph: GraphStore, nodeId: string): MemoryEdge[] {
  return Object.values(graph.edges).filter(
    (e) => e.source === nodeId || e.target === nodeId,
  );
}

function getNeighborId(edge: MemoryEdge, fromId: string): string {
  return edge.source === fromId ? edge.target : edge.source;
}

// ---------------------------------------------------------------------------
// Core graph operations
// ---------------------------------------------------------------------------

/**
 * Create or update a memory node in the session graph.
 * If a node with the same label and type exists, updates it in place.
 */
export function upsertNode(
  sessionId: string,
  type: NodeType,
  label: string,
  content: string,
  metadata?: Record<string, string>,
): MemoryNode {
  const graph = getGraph(sessionId);
  const existing = Object.values(graph.nodes).find(
    (n) => n.label === label && n.type === type,
  );

  if (existing) {
    existing.content = content;
    existing.lastAccessed = Date.now();
    existing.accessCount++;
    if (metadata) Object.assign(existing.metadata, metadata);
    existing.embedding = embed(`${label} ${content}`);
    return existing;
  }

  const node: MemoryNode = {
    id: generateId("mn"),
    type,
    label,
    content,
    embedding: embed(`${label} ${content}`),
    createdAt: Date.now(),
    lastAccessed: Date.now(),
    accessCount: 1,
    metadata: metadata ?? {},
  };
  graph.nodes[node.id] = node;
  return node;
}

/**
 * Create a typed edge between two nodes.
 * Deduplicates: if the same source→target→relation already exists, updates weight.
 */
export function createRelation(
  sessionId: string,
  sourceId: string,
  targetId: string,
  relation: RelationType,
  weight?: number,
  metadata?: Record<string, string>,
): MemoryEdge | null {
  const graph = getGraph(sessionId);
  if (!graph.nodes[sourceId] || !graph.nodes[targetId]) return null;

  const duplicate = Object.values(graph.edges).find(
    (e) =>
      e.source === sourceId &&
      e.target === targetId &&
      e.relation === relation,
  );

  if (duplicate) {
    duplicate.weight = weight ?? duplicate.weight;
    if (metadata) Object.assign(duplicate.metadata, metadata);
    return duplicate;
  }

  const edge: MemoryEdge = {
    id: generateId("me"),
    source: sourceId,
    target: targetId,
    relation,
    weight: weight ?? 1.0,
    createdAt: Date.now(),
    metadata: metadata ?? {},
  };
  graph.edges[edge.id] = edge;
  return edge;
}

/**
 * Semantic search with graph traversal — finds direct matches then walks
 * 1st/2nd-degree neighbors.
 */
export function searchGraph(
  sessionId: string,
  query: string,
  maxDepth: number = 1,
  topK: number = 5,
  edgeFilter?: RelationType[],
): GraphSearchResult {
  const graph = getGraph(sessionId);
  const nodes = Object.values(graph.nodes);
  if (nodes.length === 0) {
    return { direct: [], neighbors: [], totalNodes: 0, totalEdges: 0 };
  }

  const queryVec = embed(query);
  const scored = nodes
    .map((n) => ({ node: n, score: cosineSimilarity(queryVec, n.embedding) }))
    .sort((a, b) => b.score - a.score);

  const directHits = scored.slice(0, topK).map(({ node, score }) => {
    node.lastAccessed = Date.now();
    return {
      node,
      depth: 0,
      pathRelations: [] as string[],
      relevanceScore: Math.round(score * 1000) / 10,
    };
  });

  const neighborResults: TraversalResult[] = [];
  const visited = new Set(directHits.map((h) => h.node.id));

  for (const hit of directHits) {
    traverseNeighbors(
      graph, hit.node.id, queryVec, 1, maxDepth,
      [hit.node.label], visited, neighborResults, edgeFilter,
    );
  }

  neighborResults.sort((a, b) => b.relevanceScore - a.relevanceScore);

  return {
    direct: directHits,
    neighbors: neighborResults.slice(0, topK * 2),
    totalNodes: nodes.length,
    totalEdges: Object.keys(graph.edges).length,
  };
}

function traverseNeighbors(
  graph: GraphStore,
  nodeId: string,
  queryVec: number[],
  depth: number,
  maxDepth: number,
  pathLabels: string[],
  visited: Set<string>,
  results: TraversalResult[],
  edgeFilter?: RelationType[],
): void {
  if (depth > maxDepth) return;

  for (const edge of getEdgesForNode(graph, nodeId)) {
    if (edgeFilter && !edgeFilter.includes(edge.relation)) continue;
    const neighborId = getNeighborId(edge, nodeId);
    if (visited.has(neighborId)) continue;

    const neighbor = graph.nodes[neighborId];
    if (!neighbor) continue;

    visited.add(neighborId);
    const similarity = cosineSimilarity(queryVec, neighbor.embedding);
    const edgeDecay = decayWeight(edge);
    const relevance =
      similarity * 0.6 + (edgeDecay / Math.max(edge.weight, 0.01)) * 0.4;

    results.push({
      node: neighbor,
      depth,
      pathRelations: [
        ...pathLabels,
        `--[${edge.relation}]-->`,
        neighbor.label,
      ],
      relevanceScore: Math.round(relevance * 1000) / 10,
    });

    neighbor.lastAccessed = Date.now();
    traverseNeighbors(
      graph, neighborId, queryVec, depth + 1, maxDepth,
      [...pathLabels, `--[${edge.relation}]-->`, neighbor.label],
      visited, results, edgeFilter,
    );
  }
}

/**
 * Remove decayed edges (e^(-λt) below threshold) and orphan nodes
 * with low access counts.
 */
export function pruneStaleLinks(
  sessionId: string,
  threshold?: number,
): { removed: number; remaining: number } {
  const graph = getGraph(sessionId);
  const cutoff = threshold ?? STALE_THRESHOLD;
  const toRemove: string[] = [];

  for (const [edgeId, edge] of Object.entries(graph.edges)) {
    if (decayWeight(edge) < cutoff) toRemove.push(edgeId);
  }

  for (const id of toRemove) delete graph.edges[id];

  const orphanNodeIds = Object.keys(graph.nodes).filter((nodeId) => {
    const n = graph.nodes[nodeId];
    return (
      getEdgesForNode(graph, nodeId).length === 0 &&
      n.accessCount <= 1 &&
      Date.now() - n.lastAccessed > 7 * 86_400_000
    );
  });
  for (const id of orphanNodeIds) delete graph.nodes[id];

  return {
    removed: toRemove.length + orphanNodeIds.length,
    remaining: Object.keys(graph.edges).length,
  };
}

/**
 * Bulk-add nodes with auto-similarity linking (cosine ≥ 0.72 creates edges).
 */
export function addInterlinkedContext(
  sessionId: string,
  items: Array<{
    type: NodeType;
    label: string;
    content: string;
    metadata?: Record<string, string>;
  }>,
  autoLink: boolean = true,
): { nodes: MemoryNode[]; edges: MemoryEdge[] } {
  const createdNodes: MemoryNode[] = [];
  for (const item of items) {
    createdNodes.push(
      upsertNode(sessionId, item.type, item.label, item.content, item.metadata),
    );
  }

  const createdEdges: MemoryEdge[] = [];

  if (autoLink && createdNodes.length > 1) {
    for (let i = 0; i < createdNodes.length; i++) {
      for (let j = i + 1; j < createdNodes.length; j++) {
        const similarity = cosineSimilarity(
          createdNodes[i].embedding,
          createdNodes[j].embedding,
        );
        if (similarity >= SIMILARITY_THRESHOLD) {
          const edge = createRelation(
            sessionId, createdNodes[i].id, createdNodes[j].id,
            "similar_to", similarity,
          );
          if (edge) createdEdges.push(edge);
        }
      }
    }
  }

  // Also link to existing nodes
  const graph = getGraph(sessionId);
  const existingNodes = Object.values(graph.nodes)
    .filter((n) => !createdNodes.find((cn) => cn.id === n.id))
    .slice(0, 200);

  if (autoLink) {
    for (const newNode of createdNodes) {
      for (const existing of existingNodes) {
        const similarity = cosineSimilarity(
          newNode.embedding,
          existing.embedding,
        );
        if (similarity >= SIMILARITY_THRESHOLD) {
          const edge = createRelation(
            sessionId, newNode.id, existing.id, "similar_to", similarity,
          );
          if (edge) createdEdges.push(edge);
        }
      }
    }
  }

  return { nodes: createdNodes, edges: createdEdges };
}

/**
 * Start from a node and walk outward — returns all reachable neighbors
 * scored by decay and depth.
 */
export function retrieveWithTraversal(
  sessionId: string,
  startNodeId: string,
  maxDepth: number = 2,
  edgeFilter?: RelationType[],
): TraversalResult[] {
  const graph = getGraph(sessionId);
  const startNode = graph.nodes[startNodeId];
  if (!startNode) return [];

  startNode.lastAccessed = Date.now();
  startNode.accessCount++;

  const results: TraversalResult[] = [
    {
      node: startNode,
      depth: 0,
      pathRelations: [startNode.label],
      relevanceScore: 100,
    },
  ];

  const visited = new Set([startNodeId]);
  collectTraversal(
    graph, startNodeId, 1, maxDepth, [startNode.label],
    visited, results, edgeFilter,
  );

  return results;
}

function collectTraversal(
  graph: GraphStore,
  nodeId: string,
  depth: number,
  maxDepth: number,
  pathLabels: string[],
  visited: Set<string>,
  results: TraversalResult[],
  edgeFilter?: RelationType[],
): void {
  if (depth > maxDepth) return;

  for (const edge of getEdgesForNode(graph, nodeId)) {
    if (edgeFilter && !edgeFilter.includes(edge.relation)) continue;
    const neighborId = getNeighborId(edge, nodeId);
    if (visited.has(neighborId)) continue;

    const neighbor = graph.nodes[neighborId];
    if (!neighbor) continue;

    visited.add(neighborId);
    neighbor.lastAccessed = Date.now();

    const decayed = decayWeight(edge);
    const depthPenalty = 1 / (1 + depth * 0.3);
    const score = decayed * depthPenalty * 100;

    results.push({
      node: neighbor,
      depth,
      pathRelations: [
        ...pathLabels,
        `--[${edge.relation}]-->`,
        neighbor.label,
      ],
      relevanceScore: Math.round(score * 10) / 10,
    });

    collectTraversal(
      graph, neighborId, depth + 1, maxDepth,
      [...pathLabels, `--[${edge.relation}]-->`, neighbor.label],
      visited, results, edgeFilter,
    );
  }
}

/**
 * Get summary statistics for the session's memory graph.
 */
export function getGraphStats(sessionId: string): {
  nodes: number;
  edges: number;
  types: Record<string, number>;
  relations: Record<string, number>;
} {
  const graph = getGraph(sessionId);
  const types: Record<string, number> = {};
  const relations: Record<string, number> = {};

  for (const node of Object.values(graph.nodes)) {
    types[node.type] = (types[node.type] ?? 0) + 1;
  }
  for (const edge of Object.values(graph.edges)) {
    relations[edge.relation] = (relations[edge.relation] ?? 0) + 1;
  }

  return {
    nodes: Object.keys(graph.nodes).length,
    edges: Object.keys(graph.edges).length,
    types,
    relations,
  };
}

/**
 * Export the full graph for a session as a JSON-serializable object.
 */
export function exportGraph(sessionId: string): GraphStore {
  return getGraph(sessionId);
}

/**
 * Import a graph from a JSON object into a session.
 */
export function importGraph(sessionId: string, data: GraphStore): void {
  _graphStores.set(sessionId, data);
}

/**
 * Clear the graph for a session.
 */
export function clearGraph(sessionId: string): number {
  const graph = _graphStores.get(sessionId);
  if (!graph) return 0;
  const count =
    Object.keys(graph.nodes).length + Object.keys(graph.edges).length;
  _graphStores.delete(sessionId);
  return count;
}
