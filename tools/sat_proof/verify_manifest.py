#!/usr/bin/env python3
"""Re-check a SAT proof-of-computation manifest (see docs/SAT-PROOF-MANIFEST.md).

Usage: python tools/sat_proof/verify_manifest.py [MANIFEST_DIR] [--expect-root HEX] [--hash-only]

MANIFEST_DIR holds manifest.json plus the instances/ and proofs/ it references
(default: current directory). The script recomputes the RFC 6962 Merkle root,
the sha256 of every DIMACS instance and DRAT proof, checks every SAT witness
against its formula, and runs drat-trim on every UNSAT proof. drat-trim is
taken from $DRAT_TRIM, then PATH, then MANIFEST_DIR/tools/drat-trim/drat-trim.

The root stored in the manifest only shows internal consistency. Pass the
independently published root with --expect-root to bind the files to it.
Without drat-trim the script fails unless --hash-only is given, in which case
UNSAT proofs are only hash-checked and the run is reported as partial.
Exit status 0 means everything checked matched.
"""
import hashlib, json, os, shutil, subprocess, sys
from pathlib import Path

args = sys.argv[1:]
hash_only = "--hash-only" in args
expect_root = None
if "--expect-root" in args:
    i = args.index("--expect-root")
    expect_root = args[i + 1].lower()
    del args[i:i + 2]
args = [a for a in args if a != "--hash-only"]
ROOT = Path(args[0] if args else ".").resolve()
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
print("merkle root", root, "matches manifest" if ok else "MISMATCH with manifest")
if expect_root is None:
    print("no --expect-root given: this only shows the manifest is internally consistent")
else:
    ok = ok and root == expect_root
    print("expected root", expect_root, "MATCH" if root == expect_root else "MISMATCH")

drat = os.environ.get("DRAT_TRIM") or shutil.which("drat-trim") or str(ROOT / "tools/drat-trim/drat-trim")
have_drat = Path(drat).exists()
if not have_drat:
    print("drat-trim not found; UNSAT proofs are hash-checked only" + ("" if hash_only else " -> FAIL (pass --hash-only to accept a partial check)"))
    if not hash_only:
        ok = False


def parse_dimacs(text):
    """Return (n, clauses). Skips comment lines anywhere; clauses may span lines."""
    n, tokens = None, []
    for line in text.splitlines():
        t = line.split()
        if not t or t[0] == "c" or t[0].startswith("%"):
            continue
        if t[0] == "p":
            n = int(t[2])
            continue
        tokens.extend(int(x) for x in t)
    clauses, cur = [], []
    for x in tokens:
        if x == 0:
            clauses.append(cur); cur = []
        else:
            cur.append(x)
    if cur:
        raise ValueError("unterminated clause")
    return n, clauses


bad = 0
for r in m["instances"]:
    cnf = (ROOT / r["dimacs_path"]).read_bytes()
    if hashlib.sha256(cnf).hexdigest() != r["dimacs_sha256"]:
        bad += 1; print("cnf hash mismatch", r["id"])
    n, clauses = parse_dimacs(cnf.decode())
    if r["decision"] == "SAT":
        w = set(r["witness"])
        if any(-l in w for l in w) or any(l == 0 or abs(l) > n for l in w):
            bad += 1; print("witness is contradictory or out of range", r["id"])
        elif not all(any(l in w for l in c) for c in clauses):
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
passed = ok and bad == 0
print("RESULT:", ("PASS (partial: UNSAT proofs hash-checked only)" if passed and not have_drat else "PASS") if passed else "FAIL")
sys.exit(0 if passed else 1)
