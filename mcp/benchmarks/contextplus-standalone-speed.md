# Context+ MCP Tools — Standalone Speed Test Results

> **Date**: 2026-04-04
> **Environment**: Linux (GitHub Actions runner), Node.js 18+, Python 3.12.3
> **Test runner**: Vitest 3.2.4 (TypeScript), pytest 9.0.2 (Python)
> **Reference repos**: [ForLoopCodes/contextplus](https://github.com/ForLoopCodes/contextplus), [drQedwards/PPM](https://github.com/drQedwards/PPM)

---

## Overview

This document benchmarks the **Context+ MCP tools in isolation** — the 6 long-term memory graph tools adapted from [Context+](https://github.com/ForLoopCodes/contextplus) — **without any `peek`/KV cache layer involved**. This shows how fast Context+'s graph operations are by themselves.

The tools measured:
- `upsert_memory_node` — create/update memory nodes with TF-IDF embeddings
- `create_relation` — create typed edges between nodes
- `search_memory_graph` — semantic search with graph traversal
- `prune_stale_links` — remove decayed edges and orphan nodes
- `add_interlinked_context` — bulk-add nodes with auto-similarity linking
- `retrieve_with_traversal` — walk outward from a node, return scored neighbors

Also benchmarks the underlying TF-IDF embedding engine (`tokenize`, `TfIdfVectorizer`, `cosineSimilarity`, `embed`).

**No KV store. No peek. No short-term cache. Pure Context+ graph speed.**

---

## Test Suite

| Suite | Framework | Tests | File |
|-------|-----------|-------|------|
| TypeScript | Vitest 3.2.4 | 27 | `__tests__/contextplus-speed.test.ts` |
| Python | pytest 9.0.2 | 27 | `tests/test_contextplus_speed.py` |

---

## TypeScript Results (5 runs)

### Overall Timing

| Run | Total Duration | Transform | Collect | Tests | Prepare |
|-----|---------------|-----------|---------|-------|---------|
| 1   | 357ms         | 67ms      | 69ms    | 59ms  | 62ms    |
| 2   | 347ms         | 64ms      | 67ms    | 59ms  | 69ms    |
| 3   | 337ms         | 63ms      | 65ms    | 58ms  | 71ms    |
| 4   | 344ms         | 63ms      | 63ms    | 58ms  | 57ms    |
| 5   | 347ms         | 62ms      | 65ms    | 58ms  | 57ms    |

**Average**: 346ms total, **58ms test execution** (27 tests)

### Per-Test Breakdown (representative run)

#### Embedding Engine (no peek, no KV)

| Test | Time | What it measures |
|------|------|-----------------|
| tokenize: 100 strings | 2ms | Raw NLP tokenization throughput |
| TfIdfVectorizer: build vocab from 50 docs | 2ms | Corpus vocabulary construction |
| TfIdfVectorizer: vectorize 50 queries against 50-doc corpus | 3ms | Query vectorization throughput |
| cosineSimilarity: 1000 vector comparisons | 1ms | Raw similarity computation |
| embed: 100 documents through global vectorizer | 5ms | End-to-end embedding pipeline |

#### `upsert_memory_node` (no peek, no KV)

| Test | Time | Scale |
|------|------|-------|
| upsert 10 nodes (cold start) | 1ms | 10 nodes |
| upsert 50 nodes | 2ms | 50 nodes |
| upsert 100 nodes | 6–7ms | 100 nodes |
| update existing nodes (50 upserts on 10 labels) | 1–2ms | 50 operations, 10 unique |
| mixed node types (concept, file, symbol, note) | 1–2ms | 40 nodes, 4 types |

#### `create_relation` (no peek, no KV)

| Test | Time | Scale |
|------|------|-------|
| create 20 edges in a chain | 1–2ms | 21 nodes, 20 edges |
| create edges with all 6 relation types | 1ms | 7 nodes, 6 edges |
| create 45 edges in fully connected 10-node cluster | 1ms | 10 nodes, 45 edges |

#### `search_memory_graph` (no peek, no KV)

| Test | Time | Scale |
|------|------|-------|
| search empty graph | 1ms | 0 nodes |
| search across 10 nodes | 1ms | 10 nodes |
| search across 50 nodes | 2ms | 50 nodes |
| search across 100 nodes with depth-2 traversal | 7–8ms | 100 nodes, 99 edges |
| 10 successive searches on same graph | 1ms | 20 nodes, 10 queries |

#### `prune_stale_links` (no peek, no KV)

| Test | Time | Scale |
|------|------|-------|
| prune on graph with 50 fresh edges | 2ms | 51 nodes, 50 edges |
| prune on empty graph | 0ms | 0 nodes |

#### `add_interlinked_context` (no peek, no KV)

| Test | Time | Scale |
|------|------|-------|
| bulk add 5 nodes with auto-linking | 1ms | 5 nodes |
| bulk add 20 nodes with auto-linking | 3–9ms | 20 nodes + O(n²) similarity |
| bulk add 10 nodes without auto-linking | 0ms | 10 nodes, no edges |

#### `retrieve_with_traversal` (no peek, no KV)

| Test | Time | Scale |
|------|------|-------|
| traverse depth-1 from root with 10 children | 0–1ms | 11 nodes returned |
| traverse depth-2 from root through 3-level tree | 1ms | 26 nodes returned |
| traverse with edge filter | 0ms | 2 nodes returned (filtered) |
| traverse depth-3 chain of 30 nodes | 1ms | 4 nodes returned |

---

## Python Results (5 runs)

| Run | Duration | Tests |
|-----|----------|-------|
| 1   | 0.06s    | 27    |
| 2   | 0.06s    | 27    |
| 3   | 0.06s    | 27    |
| 4   | 0.06s    | 27    |
| 5   | 0.06s    | 27    |

**Average**: 60ms total (27 tests)

---

## Key Findings

### Context+ is blazing fast on its own

| Operation | Scale | Time | Per-op |
|-----------|-------|------|--------|
| `upsert_memory_node` | 100 nodes | 6–7ms | ~0.07ms/node |
| `create_relation` | 45 edges (fully connected) | 1ms | ~0.02ms/edge |
| `search_memory_graph` | 100 nodes + 99 edges, depth-2 | 7–8ms | Single query |
| `search_memory_graph` | 20 nodes, 10 queries | 1ms | ~0.1ms/query |
| `add_interlinked_context` | 20 nodes with auto-link | 3–9ms | Includes O(n²) similarity |
| `retrieve_with_traversal` | 26-node tree, depth-2 | 1ms | Single traversal |
| `prune_stale_links` | 51 nodes, 50 edges | 2ms | Full graph scan |
| `embed` | 100 documents | 5ms | ~0.05ms/doc |
| `cosineSimilarity` | 1000 comparisons | 1ms | ~0.001ms/comparison |

### What this means

1. **All 6 Context+ tools complete in single-digit milliseconds**, even at 100-node scale.
2. **Semantic search across 100 nodes with depth-2 traversal takes only 7–8ms** — fast enough for real-time agent decision-making.
3. **10 successive searches on a 20-node graph take 1ms total** — repeated queries are essentially free.
4. **The TF-IDF embedding engine handles 100 documents in 5ms** — no external API latency.
5. **1000 cosine similarity comparisons take 1ms** — vector math is negligible overhead.

Context+ graph operations are already sub-millisecond per operation. When combined with PMLL's `peek()` caching (see [speed-test-results.md](./speed-test-results.md)), even these fast operations can be eliminated entirely for repeated lookups.

---

## How to Reproduce

### TypeScript

```bash
cd mcp/
npm install
npx vitest run __tests__/contextplus-speed.test.ts --reporter=verbose
```

### Python

```bash
cd mcp/
pip install pytest
python3 -m pytest tests/test_contextplus_speed.py -v
```

### Benchmark loop (5 runs)

```bash
cd mcp/
for i in 1 2 3 4 5; do
  echo "--- Run $i ---"
  npx vitest run __tests__/contextplus-speed.test.ts --reporter=verbose 2>&1 | grep -E '(✓|Duration)'
done
```
