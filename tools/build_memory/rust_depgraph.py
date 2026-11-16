#!/usr/bin/env python3
"""Rust workspace -> PMLL build_memory units format, from `cargo metadata --no-deps`.
One unit per workspace crate (path = crate dir), edges = path deps on other workspace crates.
Usage: rust_depgraph.py <workspace> --out units.json --graph graph.json"""
import argparse, hashlib, json, os, subprocess, datetime
ap = argparse.ArgumentParser(); ap.add_argument("root"); ap.add_argument("--out", default="units.json"); ap.add_argument("--graph", default="graph.json")
a = ap.parse_args(); root = os.path.realpath(a.root)
md = json.loads(subprocess.check_output(["cargo", "metadata", "--no-deps", "--format-version", "1", "--offline"], cwd=root))
rel = lambda p: os.path.relpath(p, root)
pk = {p["name"]: p for p in md["packages"]}
dirof = {n: rel(os.path.dirname(p["manifest_path"])) for n, p in pk.items()}
units, nodes, edges = [], [], []
for n, p in sorted(pk.items()):
    mf = p["manifest_path"]; d = dirof[n]
    deps = sorted({dirof[x["name"]] for x in p["dependencies"] if x.get("path") and x["name"] in pk and x["name"] != n})
    units.append({"path": d, "module": n, "sha256": hashlib.sha256(open(mf, "rb").read()).hexdigest(),
                  "files": [rel(mf)], "includes": [], "depends_on_units": deps, "kind": "rust",
                  "required": False, "ok": True, "build_ok": True, "warnings": 0, "first_errors": [],
                  "targets": sorted({k for t in p["targets"] for k in t["kind"]})})
    nodes.append({"type": "crate", "id": f"rust:crate:{n}", "path": d})
    edges += [{"from": f"rust:crate:{n}", "to": f"rust:crate:{x['name']}", "kind": x.get("kind") or "normal"}
              for x in p["dependencies"] if x.get("path") and x["name"] in pk and x["name"] != n]
head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
meta = {"repo": os.path.basename(root), "head": head, "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "parser": "cargo metadata --no-deps", "workspace_members": len(md["workspace_members"])}
json.dump({"units": units, "required_failures": 0, "meta": meta}, open(a.out, "w"), indent=2)
json.dump({"meta": meta, "nodes": nodes, "edges": edges}, open(a.graph, "w"), indent=2)
print(f"crates {len(units)} edges {len(edges)}")
