#!/usr/bin/env python3
"""Append keyhunt #71 progress to coverage_ledger.json; optionally anchor digest on Sepolia PmllAnchor.
--resume: only if found.txt AND KEYFOUNDKEYFOUND.txt are empty, kill keyhunt and restart from ledger end."""
import argparse, hashlib, json, os, re, signal, subprocess, sys, time
from datetime import datetime
D = os.path.dirname(os.path.abspath(__file__))
P = lambda f: os.path.join(D, f)
ANCHOR = "0x37Da96f2a88Ae7E67A7FB305891a8c433B8B5C8D"
RPC = os.environ.get("SEPOLIA_RPC", "https://ethereum-sepolia-rpc.publicnode.com")
OVERLAP = 0.01

def latest_total():
    m = re.findall(r"Total (\d+) keys in (\d+) seconds", open(P("run.log"), errors="ignore").read())
    if not m: sys.exit("no Total line in run.log")
    return int(m[-1][0]), int(m[-1][1])

def digest(ledger):
    return hashlib.sha256(json.dumps(ledger, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def found_empty():
    return all(not os.path.exists(P(f)) or os.path.getsize(P(f)) == 0 for f in ("found.txt", "KEYFOUNDKEYFOUND.txt"))

def checkpoint():
    L = json.load(open(P("coverage_ledger.json")))
    start, end = open(P("subrange.txt")).read().split()
    total, secs = latest_total()
    base = int(start, 16)
    covered = int(total * (1 - OVERLAP))
    last_to = int(L["ranges"][-1]["to"], 16)
    seg_end = base + covered
    if seg_end <= last_to:
        print("nothing new to append"); return L
    L["ranges"].append({"from": hex(max(last_to, base)), "to": hex(seg_end), "keys": seg_end - max(last_to, base),
        "found": not found_empty(), "run_total_keys": total, "run_seconds": secs, "overlap_backoff": OVERLAP,
        "closed_at": datetime.now().astimezone().isoformat(timespec="seconds")})
    L.pop("sha256", None)
    L["sha256"] = digest(L)
    json.dump(L, open(P("coverage_ledger.json"), "w"), indent=1)
    print(f"appended {L['ranges'][-1]['from']}..{L['ranges'][-1]['to']} ({L['ranges'][-1]['keys']} keys); sha256 {L['sha256']}")
    return L

def anchor(L):
    n = len(L["ranges"])
    rid = "0x" + hashlib.sha256(f"pmll:btc-puzzle:71:coverage-ledger:{n}".encode()).hexdigest()
    dig = "0x" + L["sha256"]
    pk = json.load(open(os.path.expanduser("~/.pmll-keys/sepolia.json")))["data"][0]["private_key"]
    env = dict(os.environ, ETH_PRIVATE_KEY=pk)
    out = subprocess.run(["cast", "send", "--json", "--private-key", pk, "--rpc-url", RPC, ANCHOR, "store(bytes32,bytes32)", rid, dig],
                         env=env, capture_output=True, text=True)
    if out.returncode: sys.exit("cast send failed: " + out.stderr.replace(pk, "<redacted>")[:500] + out.stdout.replace(pk, "<redacted>")[:300])
    r = json.loads(out.stdout)
    got = subprocess.run(["cast", "call", "--rpc-url", RPC, ANCHOR, "get(bytes32)", rid], capture_output=True, text=True).stdout.strip()
    got = "0x" + got[-64:]  # get() returns (bool exists, bytes32 digest)
    rec = {"id": rid, "digest": dig, "tx": r["transactionHash"], "block": int(r["blockNumber"], 16), "status": int(r["status"], 16), "readback": got, "match": got.lower() == dig.lower()}
    print(json.dumps(rec, indent=1))
    json.dump(rec, open(P(f"anchor_ledger_{n}.json"), "w"), indent=1)
    return rec

def resume(L):
    if not found_empty(): sys.exit("found file non-empty: refusing to restart keyhunt")
    pid = int(open(P("pid")).read().strip())
    try: os.kill(pid, signal.SIGTERM); time.sleep(3)
    except ProcessLookupError: pass
    start = L["ranges"][-1]["to"][2:]
    _, end = open(P("subrange.txt")).read().split()
    open(P("subrange.txt"), "w").write(f"{start} {end}\n")
    log = open(P("run.log"), "w")
    p = subprocess.Popen(["nice", "-n", "19", "./keyhunt/keyhunt", "-m", "address", "-f", "p71.txt", "-r", start, end,
                          "-t", "6", "-l", "compress", "-s", "30"], cwd=D, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    open(P("pid"), "w").write(str(p.pid))
    print("restarted keyhunt pid", p.pid, "from", start)

if __name__ == "__main__":
    a = argparse.ArgumentParser(); a.add_argument("--anchor", action="store_true"); a.add_argument("--resume", action="store_true"); a.add_argument("--no-append", action="store_true")
    o = a.parse_args()
    L = json.load(open(P("coverage_ledger.json"))) if o.no_append else checkpoint()
    if o.anchor: anchor(L)
    if o.resume: resume(L)
