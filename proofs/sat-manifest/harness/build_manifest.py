#!/usr/bin/env python3
"""Build the draft SAT proof-of-computation manifest. Read-only on GitHub; writes only under /workspace/sat-proof."""
import hashlib, importlib.util, json, os, platform, random, subprocess, sys, datetime
from collections import deque
from pathlib import Path

ROOT = Path("/workspace/sat-proof")
PMLL = ROOT / "pmll-3sat"           # drQedwards/pmll @ 8e49955 (PR #23 head)
MATH = Path("/workspace/math")      # drQedwards/math @ 6a5264c (main, PR #2 merged)
DRAT = ROOT / "tools/drat-trim/drat-trim"
INST = ROOT / "instances"; PROOF = ROOT / "proofs"
INST.mkdir(exist_ok=True); PROOF.mkdir(exist_ok=True)
sys.path.insert(0, str(ROOT))
from drup_dpll import solve_with_proof

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod

p3 = load("pmll_three_sat", PMLL / "three_sat.py")
p2 = load("pmll_two_sat", PMLL / "two_sat.py")
m3 = load("math_three_sat", MATH / "src/three_sat.py")
m2 = load("math_two_sat", MATH / "src/two_sat.py")
t3 = load("math_test_three_sat", MATH / "tests/test_three_sat.py")
t2 = load("math_test_two_sat", MATH / "tests/test_two_sat.py")

sha = lambda b: hashlib.sha256(b).hexdigest()
def git(repo, *a): return subprocess.check_output(["git", "-C", str(repo), *a], text=True).strip()
def canon(o): return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()

def dimacs(n, clauses):
    return ("p cnf %d %d\n" % (n, len(clauses)) + "".join(" ".join(map(str, c)) + " 0\n" for c in clauses)).encode()

def brute(n, clauses):
    for mask in range(1 << n):
        a = [((mask >> i) & 1) == 1 for i in range(n)]
        if all(any((a[l-1] if l > 0 else not a[-l-1]) for l in c) for c in clauses): return a
    return None

def check_witness(clauses, lits):
    s = set(lits)
    return all(any(l in s for l in c) for c in clauses)

def implication_cert(n, clauses, var):
    """Short UNSAT certificate for 2-SAT: paths x ->* -x and -x ->* x in the implication graph.
    Each edge (u -> v) is justified by clause index i with clause == (-u v)."""
    adj = {}
    for i, (a, b) in enumerate(clauses):
        adj.setdefault(-a, []).append((b, i)); adj.setdefault(-b, []).append((a, i))
    def path(s, t):
        prev = {s: None}; q = deque([s])
        while q:
            u = q.popleft()
            if u == t and u != s or (u == t and s == t and prev[u] is not None): break
            for v, i in adj.get(u, []):
                if v not in prev: prev[v] = (u, i); q.append(v)
        if t not in prev: return None
        out = []; v = t
        while prev[v] is not None:
            u, i = prev[v]; out.append([u, v, i]); v = u
        return out[::-1]
    x = var + 1
    return {"variable": x, "path_x_to_not_x": path(x, -x), "path_not_x_to_x": path(-x, x)}

def verify_implication_cert(clauses, cert):
    x = cert["variable"]
    for p, s, t in ((cert["path_x_to_not_x"], x, -x), (cert["path_not_x_to_x"], -x, x)):
        if not p or p[0][0] != s or p[-1][1] != t: return False
        for k, (u, v, i) in enumerate(p):
            if k and p[k-1][1] != u: return False
            if sorted(clauses[i]) != sorted([-u, v]): return False
    return True

def run_drat(cnf_path, proof_path):
    r = subprocess.run([str(DRAT), str(cnf_path), str(proof_path), "-t", "60"], capture_output=True, text=True)
    lines = [l for l in r.stdout.splitlines() if l.startswith("s ")]
    return lines[-1] if lines else "no status line (exit %d)" % r.returncode

instances = []
def add(iid, family, generator, n, clauses, kind):
    clauses = [list(c) for c in clauses]
    d = dimacs(n, clauses); cnf_path = INST / f"{iid}.cnf"; cnf_path.write_bytes(d)
    rec = {"id": iid, "family": family, "generator": generator, "kind": kind, "n": n, "m": len(clauses),
           "dimacs_path": str(cnf_path.relative_to(ROOT)), "dimacs_sha256": sha(d)}
    # Primary decision: pmll three_sat for 3-SAT; pmll two_sat for 2-SAT.
    r3 = p3.solve_3sat(n, clauses)
    r3m = m3.solve_3sat(n, clauses)
    mirror, proof = solve_with_proof(n, clauses)
    assert mirror == r3, f"proof mirror diverged from three_sat.py on {iid}"
    checks = {"math_repo_three_sat_same_result": r3m == r3, "drup_mirror_same_result_as_three_sat": True}
    if kind == "2sat":
        r2 = p2.solve_2sat(n, [tuple(c) for c in clauses]); r2m = m2.solve_2sat(n, [tuple(c) for c in clauses])
        checks["math_repo_two_sat_same_result"] = (r2m["sat"], r2m["assignment"]) == (r2["sat"], r2["assignment"])
        checks["two_sat_vs_three_sat_dpll_same_decision"] = r2["sat"] == r3["sat"]
        sat, assignment, solver = r2["sat"], r2["assignment"], "pmll two_sat.solve_2sat"
        rec["solver_stats"] = {"ops": r2["ops"], "components": r2["components"]}
    else:
        sat, assignment, solver = r3["sat"], r3["assignment"], "pmll three_sat.solve_3sat"
        rec["solver_stats"] = {k: r3[k] for k in ("nodes", "decisions", "units", "conflicts")}
    if n <= 16:
        checks["brute_force_decision"] = "SAT" if brute(n, clauses) is not None else "UNSAT"
        checks["brute_force_agrees"] = checks["brute_force_decision"] == ("SAT" if sat else "UNSAT")
    rec["solver"] = solver; rec["decision"] = "SAT" if sat else "UNSAT"
    if sat:
        w = [(i + 1) if v else -(i + 1) for i, v in enumerate(assignment)]
        rec["witness"] = w; rec["witness_verified"] = check_witness(clauses, w)
        assert rec["witness_verified"]
    else:
        cert = {}
        if kind == "2sat":
            ic = implication_cert(n, clauses, r2["conflict"])
            ic_ok = verify_implication_cert(clauses, ic)
            cert["implication_path"] = {"certificate": ic, "verified": ic_ok,
                "note": "x ->* not x and not x ->* x in the implication graph; each edge cites a clause index. Linear-time checkable (Aspvall-Plass-Tarjan)."}
        pb = "".join((" ".join(map(str, l)) + " 0\n") if l else "0\n" for l in proof).encode()
        pp = PROOF / f"{iid}.drat"; pp.write_bytes(pb)
        status = run_drat(cnf_path, pp)
        cert["drat"] = {"path": str(pp.relative_to(ROOT)), "sha256": sha(pb), "lemmas": len(proof),
                        "format": "DRUP (DRAT text, no deletions), emitted from the DPLL search of three_sat.py",
                        "checker": "drat-trim", "checker_status": status, "verified": status.strip() == "s VERIFIED"}
        rec["unsat_certificate"] = cert
    rec["cross_checks"] = checks
    instances.append(rec)
    return rec

# Family 002 (drQedwards/math PR #2): exact replay of tests/test_three_sat.py instances (seed 11), plus UNSAT core and empty formula.
rng = random.Random(11); k = 0
for n in (1, 2, 3, 5, 8, 10):
    for _ in range(12):
        for planted in (True, False):
            m = max(1, int((3.5 if planted else 2.0) * n))
            add(f"f002-{k:03d}", "002", f"math tests/test_three_sat.py random_3cnf seed=11 n={n} m={m} planted={planted}", n, t3.random_3cnf(n, m, rng, planted), "3sat"); k += 1
add("f002-unsat-core", "002", "three_sat.UNSAT_CORE (all 8 sign patterns on 3 vars)", 3, m3.UNSAT_CORE, "3sat")
add("f002-empty-n4", "002", "empty formula on 4 variables", 4, [], "3sat")

# Family 001 (drQedwards/math PR #1): exact replay of tests/test_two_sat.py instances (seed 7), plus the explicit 4-clause UNSAT.
rng = random.Random(7); k = 0
for n in (1, 2, 4, 6, 8, 10):
    for _ in range(20):
        for planted in (True, False):
            m = max(1, int((2.2 if planted else 1.3) * n))
            add(f"f001-{k:03d}", "001", f"math tests/test_two_sat.py random_formula seed=7 n={n} m={m} planted={planted}", n, t2.random_formula(n, m, rng, planted), "2sat"); k += 1
add("f001-explicit-unsat", "001", "(x1 v x2)(x1 v -x2)(-x1 v x2)(-x1 v -x2)", 2, [(1, 2), (1, -2), (-1, 2), (-1, -2)], "2sat")

# Extra benchmarks: uniform random 3-SAT at clause ratio 4.26 and random 2-SAT at ratio 1.0, seed 20261006.
rng = random.Random(20261006)
def uniform(n, m, w):
    out = []
    for _ in range(m):
        vs = rng.sample(range(1, n + 1), w); out.append([v if rng.random() < 0.5 else -v for v in vs])
    return out
for n in (12, 16, 20, 30, 40):
    for j in range(4):
        m = round(4.26 * n); add(f"x3-n{n}-{j}", "extra", f"uniform random 3-SAT seed=20261006 n={n} m={m}", n, uniform(n, m, 3), "3sat")
for n in (12, 16, 20, 50, 100):
    for j in range(4):
        m = n; add(f"x2-n{n}-{j}", "extra", f"uniform random 2-SAT seed=20261006 n={n} m={m}", n, uniform(n, m, 2), "2sat")

# Tests
def run_test(cmd, cwd):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    out = r.stdout + r.stderr
    return {"command": " ".join(cmd), "cwd": str(cwd), "exit_code": r.returncode, "output": out, "output_sha256": sha(out.encode())}
py = sys.executable
tests = [run_test(["python3", "tests/test_two_sat.py"], PMLL), run_test(["python3", "tests/test_three_sat.py"], PMLL),
         run_test(["python3", "tests/test_two_sat.py"], MATH), run_test(["python3", "tests/test_three_sat.py"], MATH)]
pt = run_test([str(ROOT / ".venv/bin/python"), "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_two_sat.py", "tests/test_three_sat.py"], PMLL)
pt["note"] = "pytest summary includes wall-clock time, so this output digest is not reproducible byte-for-byte; the plain-python runs above are."
tests.append(pt)

def file_entries(repo, commit, paths):
    out = []
    for p in paths:
        b = (repo / p).read_bytes()
        out.append({"path": p, "git_blob_sha1": git(repo, "rev-parse", f"{commit}:{p}"), "sha256": sha(b), "bytes": len(b)})
    return out

pmll_commit = git(PMLL, "rev-parse", "HEAD"); math_commit = git(MATH, "rev-parse", "HEAD")
sources = {
  "pmll": {"repo": "drQedwards/pmll", "commit": pmll_commit, "ref": "3-sat-exact (PR #23 head)",
           "note": "PR #22 merged as 64ff88d; PR #23 is merged as 7bfdb9f (main). Solver files are byte-identical at 8e49955 and 7bfdb9f.",
           "files": file_entries(PMLL, pmll_commit, ["two_sat.py", "three_sat.py", "tests/test_two_sat.py", "tests/test_three_sat.py",
                                                     "docs/TWO_SAT.md", "docs/THREE_SAT.md", "SAT.py", "SAT.h", "SAT.c"])},
  "math": {"repo": "drQedwards/math", "commit": math_commit, "ref": "main (PR #1, PR #2 merged)",
           "files": file_entries(MATH, math_commit, ["src/two_sat.py", "src/three_sat.py", "tests/test_two_sat.py", "tests/test_three_sat.py",
                                                     "README.md", "CONTENTS.md", "preprints/2-sat-linear/paper.md", "preprints/3-sat-exact/paper.md"])},
  "harness": {"files": [{"path": p, "sha256": sha((ROOT / p).read_bytes())} for p in ("build_manifest.py", "drup_dpll.py")]},
}
env = {"python": platform.python_version(), "platform": platform.platform(),
       "drat_trim": {"source": "https://github.com/marijnheule/drat-trim", "commit": git(ROOT / "tools/drat-trim", "rev-parse", "HEAD"),
                     "drat_trim_c_sha256": sha((ROOT / "tools/drat-trim/drat-trim.c").read_bytes()), "build": "gcc drat-trim.c -O2"},
       "gcc": subprocess.check_output(["gcc", "--version"], text=True).splitlines()[0]}
claims = {
  "not_a_proof_of_P_eq_NP": "This manifest is not a proof that P = NP, and not a proof that P != NP. P versus NP is open.",
  "two_sat": "2-SAT is in P; this has been known since Aspvall, Plass, Tarjan (1979). two_sat.py implements that linear-time O(n+m) procedure. Nothing new is claimed.",
  "three_sat": "3-SAT is NP-complete. three_sat.py is DPLL with unit propagation: exact on every finite 3-CNF, exponential time in the worst case, no polynomial bound claimed.",
  "scope": "Each record certifies one finite computation only: SAT decisions carry a witness checkable in linear time; UNSAT decisions carry a DRUP proof checked by drat-trim (and, for 2-SAT, an implication-path certificate). Small benchmark sizes; no performance or asymptotic claim is made from them.",
  "unsat_certificates": "DPLL UNSAT answers have no short certificate in general; the DRUP proofs here are as long as the search (one lemma per conflict).",
}

def summarize():
    s = {}
    for r in instances:
        key = r["family"] + "/" + r["kind"]; d = s.setdefault(key, {"SAT": 0, "UNSAT": 0}); d[r["decision"]] += 1
    allc = [r for r in instances]
    return {"by_family": s, "total": len(allc),
            "witnesses_verified": sum(1 for r in allc if r.get("witness_verified")),
            "unsat_total": sum(1 for r in allc if r["decision"] == "UNSAT"),
            "unsat_drat_verified": sum(1 for r in allc if r.get("unsat_certificate", {}).get("drat", {}).get("verified")),
            "unsat_2sat_implication_cert_verified": sum(1 for r in allc if r.get("unsat_certificate", {}).get("implication_path", {}).get("verified")),
            "brute_force_checked": sum(1 for r in allc if "brute_force_agrees" in r["cross_checks"]),
            "brute_force_disagreements": sum(1 for r in allc if r["cross_checks"].get("brute_force_agrees") is False),
            "math_vs_pmll_three_sat_mismatches": sum(1 for r in allc if not r["cross_checks"]["math_repo_three_sat_same_result"]),
            "math_vs_pmll_two_sat_mismatches": sum(1 for r in allc if r["cross_checks"].get("math_repo_two_sat_same_result") is False),
            "two_sat_vs_dpll_mismatches": sum(1 for r in allc if r["cross_checks"].get("two_sat_vs_three_sat_dpll_same_decision") is False)}

manifest = {"schema": "pmll-sat-proof-manifest/v0-draft", "status": "DRAFT - not anchored",
            "generated_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
            "claims": claims, "sources": sources, "environment": env, "tests": tests, "summary": summarize(), "instances": instances}

# RFC 6962 Merkle tree over canonical-JSON leaves.
def leaf_hash(b): return hashlib.sha256(b"\x00" + b).digest()
def node_hash(l, r): return hashlib.sha256(b"\x01" + l + r).digest()
def mth(hs):
    if len(hs) == 1: return hs[0]
    k = 1
    while k * 2 < len(hs): k *= 2
    return node_hash(mth(hs[:k]), mth(hs[k:]))
leaves = [("schema", {"schema": manifest["schema"], "status": manifest["status"], "generated_at": manifest["generated_at"]}),
          ("claims", claims), ("environment", env), ("summary", manifest["summary"])]
leaves += [(f"source:{repo}:{f['path']}", {"repo": sources[repo].get("repo", repo), "commit": sources[repo].get("commit"), **f}) for repo in ("pmll", "math", "harness") for f in sources[repo]["files"]]
leaves += [(f"test:{i}", t) for i, t in enumerate(tests)]
leaves += [(f"instance:{r['id']}", r) for r in instances]
lh = [leaf_hash(canon(v)) for _, v in leaves]
root = mth(lh).hex()
anchor_id = sha(f"drQedwards/pmll:sat-proof:3-sat-exact@{pmll_commit[:7]}:manifest-v0".encode())
manifest["merkle"] = {"algorithm": "RFC 6962 Merkle tree, SHA-256, leaf = SHA256(0x00 || canonical_json(leaf)), node = SHA256(0x01 || L || R)",
                      "canonical_json": "json.dumps(sort_keys=True, separators=(',',':'), ensure_ascii=False) UTF-8",
                      "leaf_count": len(leaves), "leaf_order_file": "merkle_leaves.json", "root_sha256": root}
manifest["anchor_draft"] = {"executed": False, "contract": "CCF3B64AXLS4OLY5RN4H4K2CFZAYNZCJQY5MKCKCVAKMZNH7G7F7XUUF", "network": "Stellar mainnet (Soroban pmll-anchor)",
    "function": "store(id: BytesN<32>, commitment: BytesN<32>) - requires admin auth (Dr. Q signs)",
    "id": anchor_id, "id_preimage": f"drQedwards/pmll:sat-proof:3-sat-exact@{pmll_commit[:7]}:manifest-v0", "commitment": root,
    "cli": f"stellar contract invoke --id CCF3B64AXLS4OLY5RN4H4K2CFZAYNZCJQY5MKCKCVAKMZNH7G7F7XUUF --source-account <DR_Q_ADMIN> --network mainnet -- store --id {anchor_id} --commitment {root}"}
(ROOT / "merkle_leaves.json").write_text(json.dumps([{"index": i, "label": l, "leaf_hash": h.hex()} for i, ((l, _), h) in enumerate(zip(leaves, lh))], indent=1))
(ROOT / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False))
print(json.dumps(manifest["summary"], indent=1)); print("root", root); print("anchor_id", anchor_id)
print("file_sha256", sha((ROOT / "manifest.json").read_bytes()))
