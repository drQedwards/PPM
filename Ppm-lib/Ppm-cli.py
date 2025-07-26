#!/usr/bin/env python3
"""
PPM CLI — single-file MVP.
Implements:
- Append-only hash-chained ledger
- Lockfile
- Snapshots / rollback
- Plan / diff (minimal)
- Attest / apply recording
- CycloneDX SBOM export
- Dependency graph (stub)
- Provenance / doctor

Run:
  python -m ppm.cli --root . init
"""

from __future__ import annotations
import argparse, os, sys, json, hashlib, time, getpass, platform, socket, uuid
from typing import Dict, Any, List

# ---------- Ledger & state ----------

LEDGER_DIRNAME = ".ppm"
LEDGER_BASENAME = "ledger.jsonl"
STATE_BASENAME  = "state.json"
LOCK_BASENAME   = "lock.json"
SNAP_DIRNAME    = "snapshots"

def _host_fingerprint() -> str:
    data = f"{platform.system()}|{platform.release()}|{socket.gethostname()}|{getpass.getuser()}"
    return hashlib.sha256(data.encode()).hexdigest()

def project_paths(root: str) -> Dict[str,str]:
    ppm_dir   = os.path.join(root, LEDGER_DIRNAME)
    ledger    = os.path.join(ppm_dir, LEDGER_BASENAME)
    state     = os.path.join(ppm_dir, STATE_BASENAME)
    lock      = os.path.join(ppm_dir, LOCK_BASENAME)
    snaps_dir = os.path.join(ppm_dir, SNAP_DIRNAME)
    return {"ppm_dir": ppm_dir, "ledger": ledger, "state": state, "lock": lock, "snaps_dir": snaps_dir}

def ensure_init(root: str):
    p = project_paths(root)
    os.makedirs(p["ppm_dir"], exist_ok=True)
    if not os.path.exists(p["state"]):
        with open(p["state"], "w") as f:
            json.dump({"last_hash": None, "created_at": time.time()}, f, indent=2)
    if not os.path.exists(p["lock"]):
        with open(p["lock"], "w") as f:
            json.dump({"packages": {}}, f, indent=2)
    if not os.path.exists(p["ledger"]):
        open(p["ledger"], "a").close()
    os.makedirs(p["snaps_dir"], exist_ok=True)
    return p

def _read_state(state_path: str) -> Dict[str,Any]:
    if not os.path.exists(state_path):
        return {"last_hash": None}
    with open(state_path, "r") as f:
        return json.load(f)

def _write_state(state_path: str, last_hash: str):
    with open(state_path, "w") as f:
        json.dump({"last_hash": last_hash, "updated_at": time.time()}, f, indent=2)

def append_entry(root: str, op: str, payload: Dict[str,Any]) -> str:
    p = ensure_init(root)
    state = _read_state(p["state"])
    entry = {
        "id": str(uuid.uuid4()),
        "timestamp": time.time(),
        "op": op,
        "payload": payload,
        "host_fingerprint": _host_fingerprint(),
        "prev": state.get("last_hash"),
    }
    encoded = json.dumps(entry, sort_keys=True).encode()
    h = hashlib.sha256(encoded).hexdigest()
    entry["hash"] = h
    with open(p["ledger"], "a") as f:
        f.write(json.dumps(entry)+"\n")
    _write_state(p["state"], h)
    return h

def load_lock(root: str) -> Dict[str,Any]:
    p = ensure_init(root)
    with open(p["lock"], "r") as f:
        return json.load(f)

def write_lock(root: str, lock: Dict[str,Any]):
    p = ensure_init(root)
    with open(p["lock"], "w") as f:
        json.dump(lock, f, indent=2, sort_keys=True)

def create_snapshot(root: str, name: str | None = None) -> str:
    p = ensure_init(root)
    snap_id = name or str(uuid.uuid4())
    snap_dir = os.path.join(p["snaps_dir"], snap_id)
    os.makedirs(snap_dir, exist_ok=True)
    import shutil
    shutil.copy2(p["lock"], os.path.join(snap_dir, "lock.json"))
    shutil.copy2(p["state"], os.path.join(snap_dir, "state.json"))
    return snap_id

def list_snapshots(root: str) -> List[str]:
    p = ensure_init(root)
    if not os.path.isdir(p["snaps_dir"]):
        return []
    return sorted(os.listdir(p["snaps_dir"]))

def restore_snapshot(root: str, snap_id: str):
    p = ensure_init(root)
    snap_dir = os.path.join(p["snaps_dir"], snap_id)
    if not os.path.isdir(snap_dir):
        raise SystemExit(f"snapshot {snap_id} not found")
    import shutil
    shutil.copy2(os.path.join(snap_dir, "lock.json"), p["lock"])
    shutil.copy2(os.path.join(snap_dir, "state.json"), p["state"])
    append_entry(root, "rollback", {"snapshot": snap_id})

# ---------- Utility ----------

def _parse_pkg(spec: str) -> Dict[str,Any]:
    if "==" in spec:
        name, ver = spec.split("==", 1)
    else:
        name, ver = spec, None
    return {"name": name.strip(), "version": ver.strip() if ver else None}

# ---------- SBOM (CycloneDX 1.5 minimal) ----------

def cyclonedx_sbom(root: str) -> Dict[str, Any]:
    lock = load_lock(root)
    components = []
    for name, meta in sorted(lock.get("packages", {}).items()):
        components.append({
            "type": "library",
            "name": name,
            "version": meta.get("version", "unknown"),
            "hashes": [{"alg": "SHA-256", "content": meta.get("sha256","")}],
            "licenses": [{"license": {"id": meta.get("license","UNKNOWN")}}],
            "purl": meta.get("purl",""),
        })
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
        "components": components,
    }

# ---------- Graph (stub) ----------

def dependency_graph(root: str) -> Dict[str, List[str]]:
    lock = load_lock(root)
    pkgs = lock.get("packages", {})
    return {name: [] for name in pkgs.keys()}

def graph_to_dot(graph: Dict[str, List[str]]) -> str:
    lines = ["digraph deps {"]
    for a, bs in graph.items():
        if not bs:
            lines.append(f'  "{a}";')
        for b in bs:
            lines.append(f'  "{a}" -> "{b}";')
    lines.append("}")
    return "\n".join(lines)

# ---------- Commands ----------

def cmd_init(args):
    p = ensure_init(args.root)
    h = append_entry(args.root, "init", {"note": "project initialized"})
    print(f"Initialized PPM at {p['ppm_dir']}\nledger hash: {h}")

def cmd_add(args):
    lock = load_lock(args.root)
    pkgs = lock.setdefault("packages", {})
    for spec in args.packages:
        meta = _parse_pkg(spec)
        name = meta["name"]
        if name in pkgs and not args.force:
            print(f"{name} already in lock; use --force to overwrite", file=sys.stderr)
            continue
        pkgs[name] = {
            "version": meta["version"] or "unresolved",
            "sha256": "",
            "license": "UNKNOWN",
            "purl": f"pkg:pypi/{name}@{meta['version'] or 'unresolved'}"
        }
        print(f"added {name} ({pkgs[name]['version']})")
    write_lock(args.root, lock)
    h = append_entry(args.root, "add", {"packages": args.packages})
    print(f"ledger hash: {h}")

def cmd_plan(args):
    lock = load_lock(args.root)
    print(json.dumps({"plan": "noop", "lock_packages": lock.get("packages", {})}, indent=2))

def cmd_diff(args):
    if not args.snapshot:
        print("No snapshot provided; nothing to diff.")
        return
    p = project_paths(args.root)
    snap_lock = os.path.join(p["snaps_dir"], args.snapshot, "lock.json")
    if not os.path.exists(snap_lock):
        raise SystemExit(f"snapshot {args.snapshot} not found")
    with open(snap_lock, "r") as f:
        old = json.load(f)
    new = load_lock(args.root)
    old_pkgs = old.get("packages", {})
    new_pkgs = new.get("packages", {})
    added = {k:v for k,v in new_pkgs.items() if k not in old_pkgs}
    removed = {k:v for k,v in old_pkgs.items() if k not in new_pkgs}
    changed = {k:(old_pkgs[k], new_pkgs[k]) for k in new_pkgs.keys() & old_pkgs.keys() if old_pkgs[k] != new_pkgs[k]}
    print(json.dumps({"added": added, "removed": removed, "changed": changed}, indent=2))

def cmd_attest(args):
    note = args.note or ""
    h = append_entry(args.root, "attest", {"note": note, "user_signature": args.sign or "UNSIGNED"})
    print(f"attested. ledger hash: {h}")

def cmd_apply(args):
    h = append_entry(args.root, "apply", {"note": args.note or ""})
    print(f"applied. ledger hash: {h}")

def cmd_snapshot(args):
    snap = create_snapshot(args.root, args.name)
    h = append_entry(args.root, "snapshot", {"snapshot": snap})
    print(f"snapshot {snap}\nledger hash: {h}")

def cmd_snapshots(args):
    snaps = list_snapshots(args.root)
    print("\n".join(snaps))

def cmd_rollback(args):
    restore_snapshot(args.root, args.snapshot)
    print(f"restored snapshot {args.snapshot}")

def cmd_graph(args):
    graph = dependency_graph(args.root)
    if args.dot:
        print(graph_to_dot(graph))
    else:
        print(json.dumps(graph, indent=2))

def cmd_sbom(args):
    doc = cyclonedx_sbom(args.root)
    if args.out:
        with open(args.out, "w") as f:
            json.dump(doc, f, indent=2)
        print(f"Wrote SBOM to {args.out}")
    else:
        print(json.dumps(doc, indent=2))

def cmd_doctor(args):
    p = project_paths(args.root)
    ok = os.path.exists(p["ledger"]) and os.path.exists(p["lock"])
    res = {"ledger_present": os.path.exists(p["ledger"]), "lock_present": os.path.exists(p["lock"]), "status": "ok" if ok else "fail"}
    print(json.dumps(res, indent=2))

def cmd_provenance(args):
    p = project_paths(args.root)
    N = args.last
    entries = []
    if os.path.exists(p["ledger"]):
        with open(p["ledger"], "r") as f:
            lines = f.readlines()[-N:]
            entries = [json.loads(x) for x in lines]
    print(json.dumps(entries, indent=2))

# ---------- Parser & main ----------

def build_parser():
    ap = argparse.ArgumentParser(prog="ppm", description="PPM — Persistent Python Manager (single-file MVP)")
    ap.add_argument("--root", default=".", help="project root")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init"); p.set_defaults(func=cmd_init)

    p = sub.add_parser("add"); p.add_argument("packages", nargs="+")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("plan"); p.set_defaults(func=cmd_plan)
    p = sub.add_parser("diff"); p.add_argument("--snapshot")
    p.set_defaults(func=cmd_diff)

    p = sub.add_parser("attest"); p.add_argument("--sign"); p.add_argument("--note")
    p.set_defaults(func=cmd_attest)

    p = sub.add_parser("apply"); p.add_argument("--note"); p.set_defaults(func=cmd_apply)

    p = sub.add_parser("snapshot"); p.add_argument("--name"); p.set_defaults(func=cmd_snapshot)
    p = sub.add_parser("snapshots"); p.set_defaults(func=cmd_snapshots)
    p = sub.add_parser("rollback"); p.add_argument("snapshot"); p.set_defaults(func=cmd_rollback)

    p = sub.add_parser("graph"); p.add_argument("--dot", action="store_true"); p.set_defaults(func=cmd_graph)

    p = sub.add_parser("sbom"); p.add_argument("--out"); p.set_defaults(func=cmd_sbom)

    p = sub.add_parser("doctor"); p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("provenance"); p.add_argument("--last", type=int, default=20); p.set_defaults(func=cmd_provenance)

    return ap

def main(argv=None):
    argv = argv or sys.argv[1:]
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)

if __name__ == "__main__":
    main()
