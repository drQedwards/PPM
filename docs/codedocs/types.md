---
title: "Types"
description: "TypeScript source-level types and interfaces used by the Node implementation in mcp/src."
---

The repository exports several useful TypeScript types from deep source modules under `mcp/src`. These are source-level exports used by the Node implementation; the package does not declare a top-level `exports` map for them, so treat these as internal-but-documented shapes rather than a guaranteed public runtime contract.

## `peek.ts`

Source file: `mcp/src/peek.ts`

```ts
export interface PeekHitResult {
  hit: true;
  value: string;
  index: number;
}

export interface PeekPendingResult {
  hit: true;
  status: "pending";
  promise_id: string;
}

export interface PeekMissResult {
  hit: false;
}

export type PeekContextResult =
  | PeekHitResult
  | PeekPendingResult
  | PeekMissResult;
```

These types model the three legal outcomes of the cache guard.

## `memory-graph.ts`

Source file: `mcp/src/memory-graph.ts`

```ts
export type NodeType = "concept" | "file" | "symbol" | "note";

export type RelationType =
  | "relates_to"
  | "depends_on"
  | "implements"
  | "references"
  | "similar_to"
  | "contains";
```

`NodeType` constrains what kind of memory node can be created, while `RelationType` constrains the legal edge kinds used by traversal and search.

```ts
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
```

`MemoryNode` is the stored semantic unit. The `embedding` field comes from `embed()`, and the access timestamps are updated during search and traversal.

```ts
export interface MemoryEdge {
  id: string;
  source: string;
  target: string;
  relation: RelationType;
  weight: number;
  createdAt: number;
  metadata: Record<string, string>;
}
```

`MemoryEdge` drives both manual relations and auto-linked similarity edges.

```ts
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
```

`TraversalResult` is used for both direct hits and neighbor exploration. `GraphSearchResult` groups those ranked collections into one response.

## `kv-store.ts`

Source file: `mcp/src/kv-store.ts`

```ts
export type PeekResult = [boolean, string | null, number | null];
```

This is the low-level tuple returned by `PMMemoryStore.peek()` before `peekContext()` converts it into a tagged object union.

## `q-promise-bridge.ts`

Source file: `mcp/src/q-promise-bridge.ts`

```ts
export type PeekPromiseResult = [boolean, string | null, string | null];
```

This tuple is the low-level status format for promise inspection.

## `graphql.ts`

Source file: `mcp/src/graphql.ts`

```ts
export interface GraphQLResponse {
  data?: Record<string, unknown> | null;
  errors?: Array<{ message: string; locations?: unknown; path?: unknown }>;
}
```

This is the parsed JSON shape returned by `executeGraphQL()`.

## When These Types Matter

- Use the `peek.ts` types when you are extending the Node guard logic.
- Use `NodeType`, `RelationType`, and the graph interfaces when you are modifying search, traversal, or auto-linking.
- Use `GraphQLResponse` when you are integrating the TypeScript GraphQL tool.

<Callout type="info">If you need a stable import contract for application code today, prefer the Python package exports from <code>pmll_memory_mcp</code>. The TypeScript types are best read as implementation documentation for the Node server in this repository.</Callout>
