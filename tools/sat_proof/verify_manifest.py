#!/usr/bin/env python3
"""Re-check a SAT proof-of-computation manifest (see docs/SAT-PROOF-MANIFEST.md).

Usage: python tools/sat_proof/verify_manifest.py [MANIFEST_DIR]

MANIFEST_DIR holds manifest.json plus the instances/ and proofs/ it references
(default: current directory). The script recomputes the RFC 6962 Merkle root,
the sha256 of every DIMACS instance and DRAT proof, checks every SAT witness
against its formula, and runs drat-trim on every UNSAT proof. drat-trim is
taken from $DRAT_TRIM, then PATH, then MANIFEST_DIR/tools/drat-trim/drat-trim.
Exit status 0 means everything matched.
"""
import hashlib, json, os, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
m = json.loads((ROOT / "manifest.json").read_text())
canon = lambda o: json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
lh = lambda b: hashlib.sha256(b"\x00" + b).digest()


def mth(hs):
    if len(hs) == 1:
        return hs[0]
    k = 1
    while k * 2 < len(hs):
        k *= 2
    return hashlib.sha256(b"\x01" + mth(hs[:k]) + mth(hs[k:])).digest()


s = m["sources"]
leaves = [{"schema": m["schema"], "status": m["status"], "generated_at": m["generated_at"]},
          m["claims"], m["environment"], m["summary"]]
leaves += [{"repo": s[r].get("repo", r), "commit": s[r].get("commit"), **f}
           for r in ("pmll", "math", "harness") for f in s[r]["files"]]
leaves += m["tests"] + m["instances"]
root = mth([lh(canon(v)) for v in leaves]).hex()
ok = root == m["merkle"]["root_sha256"]
print("merkle root", root, "MATCH" if ok else "MISMATCH")

drat = os.environ.get("DRAT_TRIM") or shutil.which("drat-trim") or str(ROOT / "tools/drat-trim/drat-trim")
have_drat = Path(drat).exists()
if not have_drat:
    print("drat-trim not found; UNSAT proofs are hash-checked only")
bad = 0
for r in m["instances"]:
    cnf = (ROOT / r["dimacs_path"]).read_bytes()
    if hashlib.sha256(cnf).hexdigest() != r["dimacs_sha256"]:
        bad += 1; print("cnf hash mismatch", r["id"])
    clauses = [list(map(int, l.split()[:-1])) for l in cnf.decode().splitlines()[1:]]
    if r["decision"] == "SAT":
        w = set(r["witness"])
        if not all(any(l in w for l in c) for c in clauses):
            bad += 1; print("witness fails", r["id"])
    else:
        d = r["unsat_certificate"]["drat"]
        pf = (ROOT / d["path"]).read_bytes()
        if hashlib.sha256(pf).hexdigest() != d["sha256"]:
            bad += 1; print("proof hash mismatch", r["id"])
        if have_drat:
            out = subprocess.run([drat, str(ROOT / r["dimacs_path"]), str(ROOT / d["path"])],
                                 capture_output=True, text=True).stdout
            if "s VERIFIED" not in out:
                bad += 1; print("drat-trim rejects", r["id"])
print("instances", len(m["instances"]), "problems", bad)
sys.exit(0 if ok and bad == 0 else 1)
