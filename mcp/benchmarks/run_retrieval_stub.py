#!/usr/bin/env python3
"""
run_retrieval_stub.py — Minimal retrieval-quality harness stub.

Seeds a tiny labeled graph in a temp SQLite DB, runs hashing-embed search
(with optional traversal), and prints precision@k / recall@k / MRR / hit@k
on that toy set.

IMPORTANT — what this measures:
  Retrieval hit rate on labeled relevant nodes (unit bench).
  It does NOT measure agent task success.

IMPORTANT — what you must NOT claim:
  Do not cite this stub (or its toy scores) as agent accuracy, product
  accuracy, or any "99%" / "99.99%" style claim. Those require a separate
  E2E agent eval plus the full required-fields table in
  benchmark_retrieval.md. This script refuses --claim-agent-accuracy.

Usage (from mcp/):
  python benchmarks/run_retrieval_stub.py
  python benchmarks/run_retrieval_stub.py --top-k 3 --depth 1
  python benchmarks/run_retrieval_stub.py --claim-agent-accuracy   # exits nonzero
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from typing import Any, Dict, List, Sequence, Set, Tuple

MCP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if MCP_DIR not in sys.path:
    sys.path.insert(0, MCP_DIR)

from pmll_memory_mcp.embeddings import reset_vectorizer
from pmll_memory_mcp.memory_graph import (
    configure_db,
    create_relation,
    search_graph,
    upsert_node,
    _graph_stores,
)


# ---------------------------------------------------------------------------
# Toy labeled dataset (synthetic coding-agent contexts)
# Schema matches benchmark_retrieval.md:
#   node:  {id_label, type, content, relevant_for: [query_ids...]}
#   query: {id, text, relevant_labels: [...], task: "retrieve"|...}
# ---------------------------------------------------------------------------

TOY_NODES: List[Dict[str, Any]] = [
    {
        "id_label": "auth_flow",
        "type": "concept",
        "content": "user authentication login password session jwt oauth",
        "relevant_for": ["q_auth"],
    },
    {
        "id_label": "auth_service.py",
        "type": "file",
        "content": "implements login logout token refresh for auth service",
        "relevant_for": ["q_auth"],
    },
    {
        "id_label": "verify_jwt",
        "type": "symbol",
        "content": "function verify_jwt validates bearer token signature claims",
        "relevant_for": ["q_auth"],
    },
    {
        "id_label": "config_loader",
        "type": "concept",
        "content": "application configuration loader env yaml defaults",
        "relevant_for": ["q_config"],
    },
    {
        "id_label": "settings.py",
        "type": "file",
        "content": "loads SETTINGS from environment and yaml config files",
        "relevant_for": ["q_config"],
    },
    {
        "id_label": "load_config",
        "type": "symbol",
        "content": "function load_config merges env overrides into settings",
        "relevant_for": ["q_config"],
    },
    {
        "id_label": "test_helpers",
        "type": "note",
        "content": "pytest fixtures for mocking http client and db session",
        "relevant_for": ["q_test"],
    },
    {
        "id_label": "conftest.py",
        "type": "file",
        "content": "shared fixtures client db_session mock_auth for tests",
        "relevant_for": ["q_test"],
    },
    {
        "id_label": "api_handler",
        "type": "concept",
        "content": "http api request handler routing middleware responses",
        "relevant_for": ["q_api"],
    },
    {
        "id_label": "handle_request",
        "type": "symbol",
        "content": "async handle_request dispatches route to controller",
        "relevant_for": ["q_api"],
    },
]

TOY_EDGES: List[Tuple[str, str, str]] = [
    # (src id_label, tgt id_label, relation)
    ("auth_service.py", "auth_flow", "implements"),
    ("verify_jwt", "auth_flow", "references"),
    ("verify_jwt", "auth_service.py", "depends_on"),
    ("settings.py", "config_loader", "implements"),
    ("load_config", "config_loader", "references"),
    ("conftest.py", "test_helpers", "implements"),
    ("handle_request", "api_handler", "implements"),
]

TOY_QUERIES: List[Dict[str, Any]] = [
    {
        "id": "q_auth",
        "text": "how does user login and jwt auth work?",
        "relevant_labels": ["auth_flow", "auth_service.py", "verify_jwt"],
        "task": "retrieve",
    },
    {
        "id": "q_config",
        "text": "where is configuration loaded from env?",
        "relevant_labels": ["config_loader", "settings.py", "load_config"],
        "task": "retrieve",
    },
    {
        "id": "q_test",
        "text": "pytest fixtures for http client mocks",
        "relevant_labels": ["test_helpers", "conftest.py"],
        "task": "retrieve",
    },
    {
        "id": "q_api",
        "text": "api request routing handler",
        "relevant_labels": ["api_handler", "handle_request"],
        "task": "retrieve",
    },
]


def _validate_toy_dataset() -> None:
    """Ensure query ids exist, every query has a task, and labels cross-check."""
    query_ids = {q["id"] for q in TOY_QUERIES}
    node_labels = {n["id_label"] for n in TOY_NODES}

    for q in TOY_QUERIES:
        if not q.get("id"):
            raise ValueError(f"query missing id: {q!r}")
        if not q.get("task"):
            raise ValueError(f"query {q['id']!r} missing required task field")
        for lab in q.get("relevant_labels", []):
            if lab not in node_labels:
                raise ValueError(
                    f"query {q['id']!r} relevant_labels has unknown label {lab!r}"
                )

    for n in TOY_NODES:
        for qid in n.get("relevant_for", []):
            if qid not in query_ids:
                raise ValueError(
                    f"node {n['id_label']!r} relevant_for has unknown query id {qid!r}"
                )

    for src, tgt, _rel in TOY_EDGES:
        if src not in node_labels or tgt not in node_labels:
            raise ValueError(f"edge references unknown label: {(src, tgt)!r}")


def _refuse_agent_accuracy_claim() -> None:
    print(
        "REFUSING: this harness measures retrieval hit rate on labeled nodes "
        "(precision@k / recall@k / MRR). It does NOT measure agent task success.\n"
        "Do not claim agent 99% / 99.99% (or any agent accuracy %) from this "
        "stub alone. See benchmarks/benchmark_retrieval.md.",
        file=sys.stderr,
    )
    sys.exit(2)


def seed_toy_graph(session_id: str) -> Dict[str, str]:
    """Insert toy nodes/edges; return id_label -> node_id map."""
    label_to_id: Dict[str, str] = {}
    for node in TOY_NODES:
        upserted = upsert_node(
            session_id,
            node["type"],
            node["id_label"],
            node["content"],
        )  # type: ignore[arg-type]
        label_to_id[node["id_label"]] = upserted.id
    for src, tgt, rel in TOY_EDGES:
        create_relation(
            session_id,
            label_to_id[src],
            label_to_id[tgt],
            rel,  # type: ignore[arg-type]
        )
    return label_to_id


def _retrieved_labels(session_id: str, query: str, top_k: int, depth: int) -> List[str]:
    result = search_graph(session_id, query, max_depth=depth, top_k=top_k)
    # Rank after merging direct+neighbor hits so depth>0 traversal is measurable.
    by_label: Dict[str, Any] = {}
    for hit in list(result.direct) + list(result.neighbors):
        lab = hit.node.label
        if lab not in by_label:  # first/highest wins
            by_label[lab] = hit
    ranked = sorted(by_label.values(), key=lambda h: h.relevance_score, reverse=True)
    return [h.node.label for h in ranked[:top_k]]


def precision_at_k(retrieved: Sequence[str], relevant: Set[str], k: int) -> float:
    top = list(retrieved)[:k]
    if k <= 0:
        return 0.0
    return sum(1 for x in top if x in relevant) / float(k)


def recall_at_k(retrieved: Sequence[str], relevant: Set[str], k: int) -> float:
    if not relevant:
        return 0.0
    top = set(list(retrieved)[:k])
    return len(top & relevant) / float(len(relevant))


def hit_at_k(retrieved: Sequence[str], relevant: Set[str], k: int) -> float:
    top = set(list(retrieved)[:k])
    return 1.0 if top & relevant else 0.0


def reciprocal_rank(retrieved: Sequence[str], relevant: Set[str]) -> float:
    for i, lab in enumerate(retrieved, start=1):
        if lab in relevant:
            return 1.0 / float(i)
    return 0.0


def run_bench(top_k: int, depth: int) -> int:
    _validate_toy_dataset()
    reset_vectorizer()
    _graph_stores.clear()
    with tempfile.TemporaryDirectory(prefix="pmll-retr-bench-") as tmp:
        db_path = os.path.join(tmp, "graph.sqlite3")
        configure_db(db_path)
        session_id = "bench-retrieval-stub"
        seed_toy_graph(session_id)

        rows = []
        for query in TOY_QUERIES:
            relevant = set(query["relevant_labels"])
            retrieved = _retrieved_labels(
                session_id, query["text"], top_k=top_k, depth=depth
            )
            rows.append(
                {
                    "id": query["id"],
                    "query": query["text"],
                    "task": query["task"],
                    "relevant": sorted(relevant),
                    "retrieved": retrieved,
                    "p@k": precision_at_k(retrieved, relevant, top_k),
                    "r@k": recall_at_k(retrieved, relevant, top_k),
                    "hit@k": hit_at_k(retrieved, relevant, top_k),
                    "rr": reciprocal_rank(retrieved, relevant),
                }
            )

        n = len(rows)
        mean_p = sum(r["p@k"] for r in rows) / n
        mean_r = sum(r["r@k"] for r in rows) / n
        mean_hit = sum(r["hit@k"] for r in rows) / n
        mrr = sum(r["rr"] for r in rows) / n

        print("=== PMLL retrieval-quality stub (TOY set) ===")
        print(f"db={db_path}")
        print(f"config: top_k={top_k} max_depth={depth} n_queries={n}")
        print(f"baseline: hashing{'+' if depth > 0 else '_only'}{'traversal' if depth > 0 else ''}")
        print()
        for r in rows:
            print(f"Q[{r['id']}/{r['task']}]: {r['query']}")
            print(f"  relevant:  {r['relevant']}")
            print(f"  retrieved: {r['retrieved']}")
            print(
                f"  P@{top_k}={r['p@k']:.3f}  R@{top_k}={r['r@k']:.3f}  "
                f"hit@{top_k}={r['hit@k']:.0f}  RR={r['rr']:.3f}"
            )
        print()
        print(
            f"MEAN  P@{top_k}={mean_p:.3f}  R@{top_k}={mean_r:.3f}  "
            f"hit@{top_k}={mean_hit:.3f}  MRR={mrr:.3f}"
        )
        print()
        print(
            "NOTE: toy scores only. Accuracy here = retrieval hit rate on "
            "labeled nodes — NOT agent task success. See benchmark_retrieval.md."
        )
    return 0


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top-k", type=int, default=5, help="k for precision/recall/hit")
    parser.add_argument(
        "--depth",
        type=int,
        default=1,
        help="search_graph max_depth (0=hashing-only, >=1=hashing+traversal)",
    )
    parser.add_argument(
        "--claim-agent-accuracy",
        action="store_true",
        help="If set, refuse loudly (exit 2). Agent 99%% cannot come from this stub.",
    )
    args = parser.parse_args(argv)
    if args.claim_agent_accuracy:
        _refuse_agent_accuracy_claim()
    if args.top_k < 1:
        print("--top-k must be >= 1", file=sys.stderr)
        return 2
    if args.depth < 0:
        print("--depth must be >= 0", file=sys.stderr)
        return 2
    return run_bench(top_k=args.top_k, depth=args.depth)


if __name__ == "__main__":
    raise SystemExit(main())
