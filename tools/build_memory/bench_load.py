#!/usr/bin/env python3
"""Time load_sqlite on a memory_nodes.json, replicated 1x/2x/4x/8x.

    python tools/build_memory/bench_load.py memory_nodes.json --scales 1 2 4 8

Each copy k gets labels suffixed with "#k", so the graph grows by whole
copies. Every scale loads into a fresh SQLite file in a temp directory.
``--pmll-root`` points at another checkout (e.g. an older commit) to time
its build_to_memory/memory_graph instead of this one's.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import tempfile
import time
from pathlib import Path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("nodes_json")
    ap.add_argument("--scales", type=int, nargs="+", default=[1, 2, 4, 8])
    ap.add_argument("--repeat", type=int, default=1, help="runs per scale; the minimum is reported")
    ap.add_argument("--pmll-root", default=str(Path(__file__).resolve().parents[2]))
    args = ap.parse_args(argv)
    root = Path(args.pmll_root).resolve()
    spec = importlib.util.spec_from_file_location("btm_bench", root / "tools/build_memory/build_to_memory.py")
    btm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(btm)
    data = json.loads(Path(args.nodes_json).read_text())
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for k in args.scales:
            nodes, edges = {}, []
            for i in range(k):
                for n in data["nodes"]:
                    m = dict(n, label=f"{n['label']}#{i}")
                    nodes[m["label"]] = m
                edges += [(e["source"] + f"#{i}", e["target"] + f"#{i}", e["relation"]) for e in data["edges"]]
            best = None
            for r in range(args.repeat):
                db = os.path.join(tmp, f"bench_{k}_{r}.sqlite3")
                t = time.perf_counter()
                info = btm.load_sqlite(db, "bench", nodes, edges, root)
                dt = time.perf_counter() - t
                best = dt if best is None else min(best, dt)
            rows.append({"scale": k, "nodes": info["nodes"], "edges": info["edges"], "seconds": round(best, 3)})
            print(json.dumps(rows[-1]), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
