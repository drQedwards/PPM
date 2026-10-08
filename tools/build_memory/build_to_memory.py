#!/usr/bin/env python3
"""Turn batch-build results into PMLL memory nodes, edges and silo keys.

Input is the JSON written by tools/build_memory/batch_build.py or by the CI
batch-build job (``units`` with path / sha256 / kind / ok / warnings /
first_errors). Output, in ``--out`` (default memory_nodes.json):

  nodes  ``{type, label, content, metadata}``, the item shape that
         upsert_memory_node / add_interlinked_context take
  edges  ``{source, target, relation}`` by node label
  kv     ``{"build:<sha256>": compact status JSON}`` for set / peek and
         the Q-promise silo loop (qpromise_from_peek -> resolve_commit)

Node labels are the stable keys, because the memory graph upserts by
(type, label):

  file     src:<sha256>          one node per unique file content
  file     path:<repo>/<path>    mutable pointer, metadata.sha256 = content last built
  concept  module:<stem>         contains -> path nodes
  note     build:<run_id>        references -> src nodes (repo HEAD, toolchain)
  src --depends_on--> src        `#include "..."` resolved inside the repo

Optional:
  --load-sqlite DB   write the graph through mcp/pmll_memory_mcp.memory_graph
                     (SQLite; survives restarts)
  --stale DB         compare stored path:* nodes with the files on disk and
                     list paths whose content changed since they were built
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]

MODULE_ALIASES = {
    "qpromise": "Q_promise", "q_promises": "Q_promise", "promises": "Q_promise", "test_qpromise": "Q_promise",
    "pmll": "PMLL", "pmll2": "PMLL", "pypm": "Pypm", "ppm": "Ppm",
    "panda": "Panda", "panda_py": "Panda", "pandas": "Panda", "pandas_bridge": "Panda",
    "torch_plugin": "Torch", "sat_c_driver": "SAT", "importresolver": "Importresolver",
}
INCLUDE_RE = re.compile(r'#\s*include\s+"([^"]+)"')


def module_of(path: str) -> str:
    stem = Path(path).stem
    return MODULE_ALIASES.get(stem.lower(), stem)


def unit_status(u: Dict[str, Any]) -> str:
    if u.get("ok") is None:
        return "skipped"
    return "ok" if u["ok"] else "fail"


def first_error(u: Dict[str, Any]) -> str:
    errs = u.get("first_errors") or []
    return errs[0][:200] if errs else ""


def _sha_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def build(results: Dict[str, Any], root: Path = ROOT,
          repo: Optional[str] = None) -> Tuple[str, Dict[str, Dict[str, Any]], List[Tuple[str, str, str]], Dict[str, str]]:
    meta = results.get("meta", {})
    repo = repo or meta.get("repo") or root.name
    units = results.get("units", [])
    run_seed = json.dumps([meta.get("head", ""), meta.get("generated_at", "")] +
                          sorted(u["sha256"] for u in units)).encode()
    run_id = hashlib.sha256(run_seed).hexdigest()[:12]
    nodes: Dict[str, Dict[str, Any]] = {}
    edges: List[Tuple[str, str, str]] = []
    kv: Dict[str, str] = {}
    members: Dict[str, List[Tuple[str, str, str]]] = {}

    def node(t: str, label: str, content: str, md: Dict[str, Any]) -> None:
        nodes[label] = {"type": t, "label": label, "content": content,
                        "metadata": {k: str(v) for k, v in md.items()}}

    built = [u for u in units if unit_status(u) != "skipped"]
    ok = sum(1 for u in built if u["ok"])
    node("note", f"build:{run_id}",
         f"Batch build of {repo} at {meta.get('head', '?')[:12]} ({meta.get('generated_at', '?')}): "
         f"{ok}/{len(built)} units OK, {len(units) - len(built)} skipped; "
         f"required failures {results.get('required_failures', '?')}.",
         {"run_id": run_id, "repo": repo, "head": meta.get("head", ""), "generated_at": meta.get("generated_at", ""),
          "gcc": meta.get("gcc", ""), "units": len(units), "ok": ok})
    for u in units:
        sha, path, st = u["sha256"], u["path"], unit_status(u)
        err = first_error(u)
        src = f"src:{sha}"
        node("file", src,
             f"{Path(path).name} [{u.get('kind', '?')}] {st.upper()}; warnings={u.get('warnings', 0)}"
             f"{'; first error: ' + err if err else ''}. Path {repo}/{path}.",
             {"sha256": sha, "status": st, "kind": u.get("kind", ""), "warnings": u.get("warnings", 0),
              "first_error": err, "required": u.get("required", False), "run_id": run_id})
        kv[f"build:{sha}"] = json.dumps({"status": st, "w": u.get("warnings", 0), "err": err[:120], "run": run_id},
                                        separators=(",", ":"))
        plabel = f"path:{repo}/{path}"
        node("file", plabel, f"{repo}/{path}: content sha256 {sha[:16]} built with status {st}",
             {"sha256": sha, "repo": repo, "path": path, "status": st, "run_id": run_id})
        edges += [(f"build:{run_id}", src, "references"), (plabel, src, "references")]
        mod = module_of(path)
        members.setdefault(mod, []).append((path, u.get("kind", ""), st))
        edges.append((f"module:{mod}", plabel, "contains"))
        p = root / path
        if u.get("kind") in ("c", "c++", "cuda") and p.is_file():
            for inc in INCLUDE_RE.findall(p.read_text(errors="replace")):
                for cand in (p.parent / inc, root / inc):
                    if cand.is_file():
                        hsha = _sha_file(cand)
                        hlabel = f"src:{hsha}"
                        if hlabel not in nodes:
                            rel = cand.resolve().relative_to(root.resolve()).as_posix()
                            node("file", hlabel, f"{cand.name} [header]. Path {repo}/{rel}.",
                                 {"sha256": hsha, "kind": "h", "path": rel, "run_id": run_id})
                        edges.append((src, hlabel, "depends_on"))
                        break
    for mod, mem in members.items():
        failing = sorted({p for p, _, s in mem if s == "fail"})
        kinds = sorted({k for _, k, _ in mem})
        node("concept", f"module:{mod}",
             f"{mod}: kinds={','.join(kinds)}; units={len(mem)}; failing={','.join(failing) or 'none'}",
             {"kinds": ",".join(kinds), "failing": len(failing), "run_id": run_id})
    return run_id, nodes, sorted(set(edges)), kv


def _graph_api(root: Path):
    sys.path.insert(0, str(root / "mcp"))
    from pmll_memory_mcp import memory_graph  # noqa: E402
    return memory_graph


def load_sqlite(db: str, session: str, nodes, edges, root: Path = ROOT) -> Dict[str, Any]:
    mg = _graph_api(root)
    mg.configure_db(db)
    ids = {label: mg.upsert_node(session, n["type"], label, n["content"], n["metadata"]).id
           for label, n in nodes.items()}
    made = sum(1 for s, t, r in edges if mg.create_relation(session, ids[s], ids[t], r) is not None)
    stats = mg.get_graph_stats(session)
    return {"nodes": stats["nodes"], "edges": stats["edges"], "edges_created": made, "db_path": stats["db_path"]}


def stale_paths(db: str, session: str, root: Path = ROOT) -> List[Dict[str, str]]:
    """path:* nodes whose stored sha256 differs from the file on disk now."""
    mg = _graph_api(root)
    mg.configure_db(db)
    graph = mg._get_graph(session)
    labels = {n.label for n in graph.nodes.values()}
    out = []
    for n in graph.nodes.values():
        if not n.label.startswith("path:") or "path" not in n.metadata:
            continue
        p = root / n.metadata["path"]
        cur = _sha_file(p) if p.is_file() else "missing"
        if cur != n.metadata.get("sha256"):
            out.append({"path": n.metadata["path"], "built_sha256": n.metadata.get("sha256", ""),
                        "current_sha256": cur, "current_content_built": str(f"src:{cur}" in labels)})
    return sorted(out, key=lambda d: d["path"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Turn batch-build results into PMLL memory nodes.")
    ap.add_argument("results", nargs="?", default="build_results.json")
    ap.add_argument("--out", default="memory_nodes.json")
    ap.add_argument("--repo", help="repo name used in path: labels (default: meta.repo or directory name)")
    ap.add_argument("--load-sqlite", metavar="DB")
    ap.add_argument("--stale", metavar="DB", help="report path nodes whose file content changed (no build)")
    ap.add_argument("--session", default="pmll-build-memory")
    args = ap.parse_args(argv)
    if args.stale:
        rows = stale_paths(args.stale, args.session)
        print(json.dumps(rows, indent=1))
        return 0
    results = json.loads(Path(args.results).read_text())
    run_id, nodes, edges, kv = build(results, ROOT, args.repo)
    Path(args.out).write_text(json.dumps({
        "run_id": run_id, "nodes": list(nodes.values()),
        "edges": [{"source": s, "target": t, "relation": r} for s, t, r in edges], "kv": kv}, indent=1))
    print(f"run {run_id}: {len(nodes)} nodes, {len(edges)} edges, {len(kv)} silo keys -> {args.out}")
    if args.load_sqlite:
        print("sqlite:", json.dumps(load_sqlite(args.load_sqlite, args.session, nodes, edges)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
