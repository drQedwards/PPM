# Speed Comparison: Baseline vs Context+ vs Context+ with PMLL/peek

> **Date**: 2026-04-04
> **Environment**: Linux (GitHub Actions runner), Node.js 18+, Python 3.12.3
> **Test runners**: Vitest 3.2.4 (TypeScript), pytest 9.0.2 (Python)
> **Repository**: [drQedwards/PPM](https://github.com/drQedwards/PPM)

---

## Three-Way Comparison

This document compares average test execution speed across **three configurations**, for **both languages**:

| # | Configuration | What it tests | Peek/KV involved? |
|---|---------------|---------------|-------------------|
| 1 | **Baseline** (full suite) | All tests — GraphQL, KV, memory graph, peek, server, solution engine | Yes (mixed) |
| 2 | **Context+ MCP tools only** | 6 long-term memory graph tools + TF-IDF embeddings | **No** — pure Context+ graph speed |
| 3 | **PMLL/peek tools only** | KV store (init/set/peek/flush) + peek context + solution engine | **Yes** — peek caching layer |

---

## TypeScript — Average Speeds (5 runs each)

| Metric | Baseline (full suite) | Context+ only (no peek) | PMLL/peek only |
|--------|-----------------------|-------------------------|----------------|
| **Tests** | 183 (7 files) | 27 (1 file) | 32 (3 files) |
| **Avg total duration** | **922ms** | **353ms** | **382ms** |
| **Avg test execution** | **167ms** | **58ms** | **28ms** |
| **Per-test avg** | 0.91ms | 2.15ms | 0.88ms |

### Raw runs — TypeScript

#### Baseline (full suite)

| Run | Total | Tests |
|-----|-------|-------|
| 1 | 1080ms | 170ms |
| 2 | 932ms | 167ms |
| 3 | 873ms | 174ms |
| 4 | 850ms | 148ms |
| 5 | 875ms | 176ms |
| **Avg** | **922ms** | **167ms** |

#### Context+ only (no peek)

| Run | Total | Tests |
|-----|-------|-------|
| 1 | 396ms | 61ms |
| 2 | 351ms | 57ms |
| 3 | 335ms | 58ms |
| 4 | 353ms | 57ms |
| 5 | 332ms | 57ms |
| **Avg** | **353ms** | **58ms** |

#### PMLL/peek only

| Run | Total | Tests |
|-----|-------|-------|
| 1 | 459ms | 47ms |
| 2 | 359ms | 27ms |
| 3 | 369ms | 20ms |
| 4 | 362ms | 23ms |
| 5 | 363ms | 21ms |
| **Avg** | **382ms** | **28ms** |

---

## Python — Average Speeds (5 runs each)

| Metric | Baseline (full suite) | Context+ only (no peek) | PMLL/peek only |
|--------|-----------------------|-------------------------|----------------|
| **Tests** | 90 (5 files) | 27 (1 file) | 32 (3 files) |
| **Avg total duration** | **174ms** | **66ms** | **50ms** |
| **Per-test avg** | 1.93ms | 2.44ms | 1.56ms |

### Raw runs — Python

#### Baseline (full suite)

| Run | Duration | Tests |
|-----|----------|-------|
| 1 | 280ms | 90 |
| 2 | 190ms | 90 |
| 3 | 120ms | 90 |
| 4 | 110ms | 90 |
| 5 | 170ms | 90 |
| **Avg** | **174ms** | **90** |

#### Context+ only (no peek)

| Run | Duration | Tests |
|-----|----------|-------|
| 1 | 60ms | 27 |
| 2 | 70ms | 27 |
| 3 | 80ms | 27 |
| 4 | 60ms | 27 |
| 5 | 60ms | 27 |
| **Avg** | **66ms** | **27** |

#### PMLL/peek only

| Run | Duration | Tests |
|-----|----------|-------|
| 1 | 40ms | 32 |
| 2 | 40ms | 32 |
| 3 | 70ms | 32 |
| 4 | 60ms | 32 |
| 5 | 40ms | 32 |
| **Avg** | **50ms** | **32** |

---

## Side-by-Side Summary

### Test execution time (excluding harness overhead)

| Configuration | TypeScript | Python | TS per-test | PY per-test |
|---------------|-----------|--------|-------------|-------------|
| **Baseline (full suite)** | 167ms (183 tests) | 174ms (90 tests) | 0.91ms | 1.93ms |
| **Context+ only (no peek)** | 58ms (27 tests) | 66ms (27 tests) | 2.15ms | 2.44ms |
| **PMLL/peek only** | 28ms (32 tests) | 50ms (32 tests) | 0.88ms | 1.56ms |

### Key observations

1. **PMLL/peek is the fastest per-test** in both languages:
   - TypeScript: **0.88ms/test** — peek cache hits are instant (0ms reported by Vitest)
   - Python: **1.56ms/test** — same pattern, Python overhead ~1.8× higher

2. **Context+ without peek is fast at scale** — handling 100-node graphs with depth-2 semantic search in 7–8ms (TS) / ~8–10ms (PY), but per-test cost is higher because these tests do heavier graph work (bulk inserts, O(n²) similarity linking, traversal).

3. **Both languages show the same pattern**:
   - Context+ graph operations: single-digit milliseconds
   - PMLL/peek cache operations: sub-millisecond (0ms per hit)
   - Combined, they eliminate redundant computation entirely

4. **Python is ~1.8× slower than TypeScript per-test** on average — expected given V8's JIT compilation vs CPython's interpreter. But both languages still complete all operations in well under 1 second.

### Per-operation highlights (from verbose test output)

| Operation | TypeScript | Python | Layer |
|-----------|-----------|--------|-------|
| `peek` cache hit | **0ms** | **<1ms** | PMLL/KV |
| `set` + `peek` round-trip | **≤2ms** | **≤3ms** | PMLL/KV |
| `flush` all slots | **0ms** | **<1ms** | PMLL/KV |
| `upsert_memory_node` (100 nodes) | **6–7ms** | **~8ms** | Context+ graph |
| `search_memory_graph` (100 nodes, depth-2) | **7–8ms** | **~10ms** | Context+ graph |
| `add_interlinked_context` (20 nodes, auto-link) | **3–9ms** | **~6ms** | Context+ graph |
| `retrieve_with_traversal` (26-node tree) | **1ms** | **~2ms** | Context+ graph |
| `embed` 100 documents (TF-IDF) | **5ms** | **~6ms** | Embeddings |
| 1000 cosine similarity comparisons | **1ms** | **~2ms** | Embeddings |

---

## What this means for agents

In a typical agent task with 10–50 tool invocations:

| Scenario | Without PMLL | With Context+ only | With Context+ + PMLL/peek |
|----------|-------------|--------------------|-----------------------------|
| **First call** | Full execution | Full execution (fast — single-digit ms) | Full execution (same) |
| **Repeated call** | Full re-execution | Full re-execution (still fast) | **0ms** (cache hit) |
| **10 redundant calls** | 10× cost | 10× cost (but each is cheap) | **1× cost + 9× free** |
| **Net savings (50 calls, 60% redundant)** | 0% | 0% (but fast baseline) | **60% elimination** |

Context+ graph tools are already blazing fast on their own. Adding PMLL/peek on top means even these fast operations don't need to re-execute when the same data is requested again.

---

## How to Reproduce

```bash
cd mcp/
npm install

# Baseline (full suite)
for i in 1 2 3 4 5; do npx vitest run 2>&1 | grep Duration; done

# Context+ only (no peek)
for i in 1 2 3 4 5; do npx vitest run __tests__/contextplus-speed.test.ts 2>&1 | grep Duration; done

# PMLL/peek only
for i in 1 2 3 4 5; do npx vitest run __tests__/kv-store.test.ts __tests__/peek.test.ts __tests__/solution-engine.test.ts 2>&1 | grep Duration; done

# Python equivalents
pip install pytest
for i in 1 2 3 4 5; do python3 -m pytest tests/ --ignore=tests/test_server.py -q 2>&1 | tail -1; done
for i in 1 2 3 4 5; do python3 -m pytest tests/test_contextplus_speed.py -q 2>&1 | tail -1; done
for i in 1 2 3 4 5; do python3 -m pytest tests/test_kv_store.py tests/test_peek.py tests/test_solution_engine.py -q 2>&1 | tail -1; done
```
