# Retrieval-quality benchmark harness (design)

This document defines how we will measure **memory-graph retrieval quality**
for `pmll_memory_mcp`. It is a unit-level retrieval bench — **not** an
end-to-end agent-success scorecard.

> **Accuracy (this harness)** = retrieval hit rate on labeled relevant nodes
> (precision@k / recall@k / MRR over synthetic queries). It is **not** agent
> task success, pass@k on coding tasks, or any product “X% accurate” claim.
> Do not cite this stub (or a future full run of this harness alone) as
> agent accuracy.

Speed benches already live beside this file (`*-speed*.md`). This harness
is the quality counterpart.

Runnable stub: [`run_retrieval_stub.py`](./run_retrieval_stub.py).

---

## Required fields for any future accuracy claim

Any published retrieval-quality number **must** record all of the following.
Claims missing a field are incomplete.

| Field | What to record |
|-------|----------------|
| **Dataset** | Synthetic coding-agent contexts: labeled `concept` / `file` / `symbol` / `note` nodes + edges. Version or hash of the seed set. |
| **Task defs** | (1) retrieve relevant node(s) given a natural-language query; (2) promote KV → graph then retrieve; (3) restart durability (write → new process / reload → retrieve). |
| **Baselines** | `no_graph` (empty / chance); `tfidf_legacy` if present; `hashing_only` (embed cosine, depth=0); `hashing+traversal` (embed + neighbor walk). Optional: vanilla KV peek / no memory. |
| **n trials** | Number of labeled queries (and bootstrap resamples if CI reported). |
| **Model / version** | **N/A** for pure retrieval unit bench (hashing embed + graph). Note separately if an agent E2E eval is attached — that is a different harness. |
| **Prompts** | **N/A** for retrieval unit. Record **retrieval config**: `top_k`, decay (`DECAY_LAMBDA`), `max_depth`, similarity / stale thresholds. |
| **Metrics** | `precision@k`, `recall@k`, `MRR` (mean reciprocal rank of first relevant hit). |
| **Confidence intervals** | Method (e.g. bootstrap percentile over queries, or Wilson for binary hit@k) + level (e.g. 95%). |
| **Comparison** | Same metrics vs vanilla KV peek / no-memory baseline on the same labeled queries. |
| **“Accuracy” definition** | Exactly: fraction of queries where a labeled relevant node appears in the top-k retrieved set (hit rate), plus the ranked metrics above — **not** agent task success. |

---

## Dataset sketch

Tiny seed (stub) and a future larger pack should share the same schema:

```text
node: {id_label, type, content, relevant_for: [query_ids...]}
edge: {source_label, target_label, relation}
query: {id, text, relevant_labels: [...], task: retrieve|promote_kv|restart}
```

Content themes: auth modules, config loaders, test helpers, API handlers —
the kinds of fragments a coding agent would store across a session.

---

## Baselines & configs

Default retrieval config for claims (override and record if changed):

- `top_k=5`
- `max_depth=0` (hashing-only) vs `max_depth=1..2` (hashing+traversal)
- `DECAY_LAMBDA` / `SIMILARITY_THRESHOLD` as in `memory_graph.py`

Baselines to report side-by-side on the same query set:

1. **no_graph** — empty store (sanity: metrics ≈ 0)
2. **hashing_only** — `search_graph(..., max_depth=0)`
3. **hashing+traversal** — `search_graph(..., max_depth≥1)`
4. **tfidf_legacy** — optional; only if a frozen TF-IDF path is exercised for comparison (not the production query path)
5. **kv_peek / no_memory** — exact-key peek or empty memory (shows graph value-add)

---

## Metrics formulas

For query \(q\) with relevant label set \(R_q\), retrieved top-\(k\) labels \(L_q\):

- \(\mathrm{precision@}k = |L_q \cap R_q| / k\) (or `/|L_q|` if fewer than \(k\) returned — record which)
- \(\mathrm{recall@}k = |L_q \cap R_q| / |R_q|\)
- \(\mathrm{hit@}k = 1\) if \(L_q \cap R_q \neq \emptyset\), else \(0\)
- \(\mathrm{MRR} = \mathrm{mean}_q\, 1/\mathrm{rank}\) of first relevant label (0 if none)

Aggregate means over queries; report CI via the method declared above.

---

## Out of scope (separate harness)

- Agent E2E task success, tool-choice quality, latency SLOs (see speed benches)
- LLM judge scores, prompt ablations
- Any “99%” / product accuracy marketing copy — **not derived from this file**

When a full labeled pack lands, link results here and keep README claims
tied to this harness definition — never invent a percentage without the
table of required fields filled in.
