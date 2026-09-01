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
from typing import Dict, List, Sequence, Set, Tuple

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
# ---------------------------------------------------------------------------

TOY_NODES: List[Tuple[str, str, str]] = [
    # (type, label, content)
    ("concept", "auth_flow", "user authentication login password session jwt oauth"),
    ("file", "auth_service.py", "implements login logout token refresh for auth service"),
    ("symbol", "verify_jwt", "function verify_jwt validates bearer token signature claims"),
    ("concept", "config_loader", "application configuration loader env yaml defaults"),
    ("file", "settings.py", "loads SETTINGS from environment and yaml config files"),
    ("symbol", "load_config", "function load_config merges env overrides into settings"),
    ("note", "test_helpers", "pytest fixtures for mocking http client and db session"),
    ("file", "conftest.py", "shared fixtures client db_session mock_auth for tests"),
    ("concept", "api_handler", "http api request handler routing middleware responses"),
    ("symbol", "handle_request", "async handle_request dispatches route to controller"),
]

TOY_EDGES: List[Tuple[str, str, str]] = [
    ("auth_service.py", "auth_flow", "implements"),
    ("verify_jwt", "auth_flow", "references"),
    ("verify_jwt", "auth_service.py", "depends_on"),
    ("settings.py", "config_loader", "implements"),
    ("load_config", "config_loader", "references"),
    ("conftest.py", "test_helpers", "implements"),
    ("handle_request", "api_handler", "implements"),
]

# query_text -> set of relevant node labels
TOY_QUERIES: List[Tuple[str, Set[str]]] = [
    ("how does user login and jwt auth work?", {"auth_flow", "auth_service.py", "verify_jwt"}),
    ("where is configuration loaded from env?", {"config_loader", "settings.py", "load_config"}),
    ("pytest fixtures for http client mocks", {"test_helpers", "conftest.py"}),
    ("api request routing handler", {"api_handler", "handle_request"}),
]


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
    """Insert toy nodes/edges; return label -> node_id map."""
    label_to_id: Dict[str, str] = {}
    for node_type, label, content in TOY_NODES:
        node = upsert_node(session_id, node_type, label, content)  # type: ignore[arg-type]
        label_to_id[label] = node.id
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
    labels: List[str] = []
    seen: Set[str] = set()
    for hit in list(result.direct) + list(result.neighbors):
        lab = hit.node.label
        if lab in seen:
            continue
        seen.add(lab)
        labels.append(lab)
        if len(labels) >= top_k:
            break
    return labels


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
    reset_vectorizer()
    _graph_stores.clear()
    with tempfile.TemporaryDirectory(prefix="pmll-retr-bench-") as tmp:
        db_path = os.path.join(tmp, "graph.sqlite3")
        configure_db(db_path)
        session_id = "bench-retrieval-stub"
        seed_toy_graph(session_id)

        rows = []
        for query, relevant in TOY_QUERIES:
            retrieved = _retrieved_labels(session_id, query, top_k=top_k, depth=depth)
            rows.append(
                {
                    "query": query,
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
            print(f"Q: {r['query']}")
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
    parser.add_argument("--top-k", type=int, default=3, help="k for precision/recall/hit")
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
