#!/usr/bin/env python3
"""Read-only claim guard for puzzle #71. NEVER broadcasts or signs anything.
(a) watches found.txt / KEYFOUNDKEYFOUND.txt; (b) on a hit writes ALERT.md (private-relay claim steps) and exits;
(c) pulls recent public activity of known sweepers/collectors (Blockscout, Ethereum + Base) and ranks
new counterparties with the siphon rich-walk edge score (siphon-walk/walk.py rich_weight) using the
learning-walk adaptive-prune best-loop weights. Writes guard_report.json.  Usage: claim_guard.py [--loop SECONDS]"""
import json, os, sys, time, urllib.request
from datetime import datetime, timezone
D = os.path.dirname(os.path.abspath(__file__))
WATCH = ["0xeeeee90971B6264C53175D3Af6840a8dD5dc7b6C", "0xf111122404b8C2FC01dfF89C65D3104fbb608008",
         "0x8566263047EaD285194B2e8Feb53F312cf8CB463", "0x09CbC0D92AABE6F53Ac7E84F0Ba0FbfD05eB80f2"]
CHAINS = {"ethereum": "https://eth.blockscout.com", "base": "https://base.blockscout.com"}
SW = "/workspace/siphon-walk"

def adaptive_W():
    r = json.load(open("/workspace/learning-walk/results.json"))["adaptive_prune_siphon"]["loops"]
    best = min(r, key=lambda l: l["mean_ratio_adaptive_over_bool"])
    return best["W"], best["loop"], best["mean_ratio_adaptive_over_bool"]

def load_scorer(G):
    """exec walk.py's feature/scoring section (everything before the walks) on graph G."""
    src = open(f"{SW}/walk.py").read().split("# --- walks ---")[0]
    src = src.replace('G = json.load(open(ROOT / "graph.json"))', "G = __G__")
    ns = {"__G__": G, "__file__": f"{SW}/walk.py", "__name__": "walk_scorer"}
    exec(compile(src, "walk.py[scoring]", "exec"), ns)
    return ns

def check_found():
    hits = [f for f in ("found.txt", "KEYFOUNDKEYFOUND.txt") if os.path.exists(os.path.join(D, f)) and os.path.getsize(os.path.join(D, f)) > 0]
    if hits:
        open(os.path.join(D, "ALERT.md"), "w").write(f"""# ALERT: keyhunt reported a hit ({', '.join(hits)}) at {datetime.now().astimezone().isoformat()}
Nothing has been broadcast. Do NOT spend via the public mempool: spending exposes the pubkey and #71 (2^70 range)
can be kangaroo-solved by bots in well under an hour, then RBF-raced.
1. Stop keyhunt; copy the key file offline; verify key -> address 1PWo3JeB9jrGwfHDNpdGK54CRas7fsVzXU locally.
2. Build + sign the sweep tx OFFLINE (bitcoin-core / python-bitcoinlib), to a fresh address you control, high fee, no RBF.
3. Submit ONLY via a private/direct-to-miner relay (e.g. MARA Slipstream submission), never a public node or explorer push.
4. Watch for confirmation; keep the raw tx private until mined.
Dr. Q must approve every step; this guard does none of it.
""")
        print("HIT -> ALERT.md written; guard stopping."); sys.exit(2)

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "pmll-claim-guard/1"})
    with urllib.request.urlopen(req, timeout=30) as r: return json.load(r)

def ts(s): return 0 if not s else int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())

def pull():
    edges, errors = [], []
    for chain, base in CHAINS.items():
        for a in WATCH:
            for kind in ("transactions", "token-transfers"):
                try: items = get(f"{base}/api/v2/addresses/{a}/{kind}").get("items", [])
                except Exception as e: errors.append(f"{chain}:{a}:{kind}:{e}"); continue
                for i in items:
                    f, t = (i.get("from") or {}).get("hash"), (i.get("to") or {}).get("hash")
                    if not f or not t: continue
                    if kind == "transactions": v = int(i.get("value") or 0) / 1e18; tx = i["hash"]; sym = "ETH"
                    else:
                        tot = i.get("total") or {}; dec = int(tot.get("decimals") or 18)
                        v = int(tot.get("value") or 0) / 10 ** dec; tx = i.get("transaction_hash"); sym = (i.get("token") or {}).get("symbol")
                    edges.append({"src": f, "dst": t, "value": v, "ts": ts(i["timestamp"]), "tx": tx, "chain": chain, "asset": sym, "watched": a})
    return edges, errors

def one_pass():
    check_found()
    G = json.load(open(f"{SW}/graph.json"))
    known = {(e.get("src") or "").lower() for e in G["edges"]} | {(e.get("dst") or "").lower() for e in G["edges"]}
    new_edges, errors = pull()
    G2 = dict(G); G2["edges"] = G["edges"] + new_edges
    S = load_scorer(G2); W, loop, ratio = adaptive_W()
    watch = {w.lower() for w in WATCH}; cps = {}
    for e in new_edges:
        s, d = e["src"].lower(), e["dst"].lower()
        cp = d if s in watch else s
        if cp in watch: continue
        sc = S["rich_weight"](S["norm"](e["src"]), S["norm"](e["dst"]), W)
        c = cps.setdefault(cp, {"address": cp, "score": 0.0, "n": 0, "dir": set(), "chains": set(), "assets": set(), "watched": set(), "new": cp not in known, "last_ts": 0})
        c["score"] = max(c["score"], sc); c["n"] += 1; c["dir"].add("out_from_watched" if s in watch else "into_watched")
        c["chains"].add(e["chain"]); c["assets"].add(str(e["asset"])); c["watched"].add(e["watched"]); c["last_ts"] = max(c["last_ts"], e["ts"])
    ranked = sorted(cps.values(), key=lambda c: (-c["score"], -c["n"]))
    for c in ranked:
        for k in ("dir", "chains", "assets", "watched"): c[k] = sorted(c[k])
        c["last_seen"] = datetime.fromtimestamp(c["last_ts"], timezone.utc).astimezone().isoformat(timespec="seconds")
    rep = {"generated": datetime.now().astimezone().isoformat(timespec="seconds"), "found_files_empty": True,
           "weights": W, "weights_from": f"learning-walk adaptive_prune_siphon loop {loop} (ratio {ratio:.3f})",
           "edges_pulled": len(new_edges), "counterparties": len(ranked), "new_counterparties": sum(c["new"] for c in ranked),
           "fetch_errors": errors, "top": ranked[:25]}
    json.dump(rep, open(os.path.join(D, "guard_report.json"), "w"), indent=1)
    return rep

if __name__ == "__main__":
    period = int(sys.argv[sys.argv.index("--loop") + 1]) if "--loop" in sys.argv else 0
    while True:
        r = one_pass()
        print(f"{r['generated']} edges={r['edges_pulled']} cps={r['counterparties']} new={r['new_counterparties']} errors={len(r['fetch_errors'])}")
        if not period: break
        for _ in range(period // 10): check_found(); time.sleep(10)
