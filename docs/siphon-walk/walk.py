#!/usr/bin/env python3
"""Rich walk vs Boolean walk on real siphon/sweep transfer graph.

Read-only experiment. Features are structural (no label bits).
Leave-one-collector-out for hyperparameter selection to measure leakage.
"""
from __future__ import annotations
import json, math, random, statistics, hashlib
from collections import defaultdict, deque, Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
G = json.load(open(ROOT / "graph.json"))

def norm(a: str | None) -> str | None:
    if not a: return None
    return a.lower() if a.startswith("0x") or a.startswith("0X") else a

COLLECTORS = [
    "0xeeeee90971b6264c53175d3af6840a8dd5dc7b6c",
    "0xf111122404b8c2fc01dff89c65d3104fbb608008",
    "0x8566263047ead285194b2e8feb53f312cf8cb463",
    "0x09cbc0d92aabe6f53ac7e84f0ba0fbfd05eb80f2",
    "FncazAs6omJJjtLVzquzT9KoyXn6tFixr9kGjr42ktLj",
    "5qmtDCvUreD8G59M5FosdpV8Gqdd3kFgdH1Vv7HKXUKq",
    "7jNPvxGzQ5wG5NMYZD1GGLAvCyYF7v1Ai5PV9whYt9AN",
]
COLLECTORS_N = [norm(c) if c.startswith("0x") else c for c in COLLECTORS]
SEEDS = [norm(s) for s in G["seeds"]["ethereum"]] + G["seeds"]["solana"]
DELEGATION = {norm(k): norm(v) for k, v in G.get("delegation", {}).items()}

# --- build multigraph ---
edges = []
for e in G["edges"]:
    s, d = norm(e.get("src")), norm(e.get("dst"))
    if not s or not d or s == d: continue
    edges.append({**e, "src": s, "dst": d})

# adjacency lists
adj = defaultdict(list)  # src -> list of edge dicts
for e in edges:
    adj[e["src"]].append(e)

nodes = set()
for e in edges:
    nodes.add(e["src"]); nodes.add(e["dst"])

# --- structural features (no collector labels) ---
# same-second in/out pairs at a node (Solana-style concurrency)
by_node_ts = defaultdict(list)  # node -> [(ts, direction, other, tx)]
for e in edges:
    ts = e.get("ts")
    if ts is None: continue
    try: ts = int(ts)
    except: continue
    by_node_ts[e["dst"]].append((ts, "in", e["src"], e.get("tx")))
    by_node_ts[e["src"]].append((ts, "out", e["dst"], e.get("tx")))

same_second_pair_count = Counter()  # (src,dst) for outs that pair with an in at same second on src
for node, evs in by_node_ts.items():
    ins = [(t, o, tx) for t, d, o, tx in evs if d == "in"]
    outs = [(t, o, tx) for t, d, o, tx in evs if d == "out"]
    in_by_t = defaultdict(list)
    for t, o, tx in ins: in_by_t[t].append((o, tx))
    for t, o, tx in outs:
        if in_by_t.get(t):
            same_second_pair_count[(node, o)] += 1

# outflow share: fraction of a node's out-value going to each neighbor
out_value = Counter()
edge_value = Counter()  # (src,dst) summed value
repeat_count = Counter()  # (src,dst) transfer count
for e in edges:
    v = float(e.get("value") or 0)
    out_value[e["src"]] += max(v, 0)
    edge_value[(e["src"], e["dst"])] += max(v, 0)
    repeat_count[(e["src"], e["dst"])] += 1

def outflow_share(s, d):
    tot = out_value[s]
    if tot <= 0: return 0.0
    return edge_value[(s, d)] / tot

# near-zero residual: after outs from a node in a time window, remaining "apparent" — proxy:
# if a node's total out approaches its total in (sweep-to-empty), flag those out edges
in_value = Counter()
for e in edges:
    in_value[e["dst"]] += max(float(e.get("value") or 0), 0)

def near_zero_residual(s, d):
    """1 if source looks swept (out ≈ in, and this edge is a large share of out)."""
    inn, out = in_value[s], out_value[s]
    if out <= 0: return 0.0
    # residual ratio
    if inn <= 0:
        # seed-like: still score large out-share
        return 1.0 if outflow_share(s, d) >= 0.5 else 0.0
    residual = max(inn - out, 0) / inn
    if residual < 0.05 and outflow_share(s, d) >= 0.1:
        return 1.0
    return 0.0

def delegation_boost(s, d):
    if DELEGATION.get(s) == d: return 1.0
    # also edges marked delegation
    return 0.0

# precompute edge weight components
def feat(s, d):
    return {
        "same_sec": float(same_second_pair_count.get((s, d), 0)),
        "out_share": outflow_share(s, d),
        "repeat": float(repeat_count[(s, d)]),
        "delegation": delegation_boost(s, d),
        "near_zero": near_zero_residual(s, d),
    }

# Default a-priori weights (from task feature list — NOT tuned on labels)
DEFAULT_W = dict(same_sec=3.0, out_share=2.0, repeat=1.0, delegation=5.0, near_zero=2.0)

def rich_weight(s, d, W=DEFAULT_W):
    f = feat(s, d)
    # memory-less edge score; walk carries visited memory separately
    score = 1e-6  # floor so graph stays connected for RW
    score += W["same_sec"] * math.log1p(f["same_sec"])
    score += W["out_share"] * f["out_share"]
    score += W["repeat"] * math.log1p(f["repeat"])
    score += W["delegation"] * f["delegation"]
    score += W["near_zero"] * f["near_zero"]
    return score

# --- walks ---
def neighbors(u):
    return adj.get(u, [])

def bfs_expand(start, target, max_expand=50000):
    """Boolean BFS: return (found, steps/depth, nodes_expanded)."""
    if start == target: return True, 0, 1
    q = deque([(start, 0)])
    seen = {start}
    expanded = 0
    while q:
        u, dist = q.popleft()
        expanded += 1
        if expanded > max_expand: return False, None, expanded
        for e in neighbors(u):
            v = e["dst"]
            if v in seen: continue
            if v == target: return True, dist + 1, expanded + 1
            seen.add(v)
            q.append((v, dist + 1))
    return False, None, expanded

def random_walk(start, target, weighted, W, max_steps=5000, rng=None):
    """Return steps to hit target or None. Memory = no immediate revisit bias via seen soft penalty."""
    rng = rng or random.Random()
    if start == target: return 0
    u = start
    seen = {u}
    for step in range(1, max_steps + 1):
        outs = neighbors(u)
        if not outs:
            # teleport to seed-ish restart
            u = start
            continue
        if weighted:
            ws = []
            for e in outs:
                v = e["dst"]
                w = rich_weight(u, v, W)
                # memory: penalize revisits
                if v in seen: w *= 0.15
                ws.append(w)
            total = sum(ws)
            r = rng.random() * total
            acc = 0.0
            v = outs[-1]["dst"]
            for e, w in zip(outs, ws):
                acc += w
                if acc >= r:
                    v = e["dst"]; break
        else:
            v = rng.choice(outs)["dst"]
        if v == target: return step
        seen.add(v)
        u = v
    return None

def greedy_expand(start, target, W, max_expand=50000):
    """Best-first by rich edge weight (Boolean counterpart = BFS)."""
    if start == target: return True, 0, 1
    # priority queue as list of (-score, counter, node, depth)
    import heapq
    counter = 0
    heap = []
    seen = {start}
    # seed fringe from start
    for e in neighbors(start):
        w = rich_weight(start, e["dst"], W)
        heapq.heappush(heap, (-w, counter, e["dst"], 1)); counter += 1
    expanded = 0
    while heap:
        negw, _, u, dist = heapq.heappop(heap)
        if u in seen and u != start:
            # may have been pushed multiple times
            pass
        if u in seen:
            continue
        seen.add(u)
        expanded += 1
        if u == target: return True, dist, expanded
        if expanded > max_expand: return False, None, expanded
        for e in neighbors(u):
            v = e["dst"]
            if v in seen: continue
            w = rich_weight(u, v, W)
            heapq.heappush(heap, (-w, counter, v, dist + 1)); counter += 1
    return False, None, expanded

# Which collectors are reachable from which seeds?
def reachable_pairs():
    pairs = []
    for seed in SEEDS:
        if seed not in nodes and seed not in adj: continue
        for c in COLLECTORS_N:
            if c not in nodes: continue
            # same-chain heuristic: eth/base vs sol
            seed_is_eth = seed.startswith("0x")
            c_is_eth = c.startswith("0x") if isinstance(c, str) else False
            if seed_is_eth != c_is_eth: continue
            ok, depth, _ = bfs_expand(seed, c)
            if ok:
                pairs.append((seed, c, depth))
    return pairs

pairs = reachable_pairs()

N_TRIALS = 200
RNG = random.Random(42)

def summarize(xs):
    xs = [x for x in xs if x is not None]
    if not xs: return dict(n=0, mean=None, stdev=None, median=None, p90=None)
    xs = sorted(xs)
    return dict(
        n=len(xs),
        mean=statistics.mean(xs),
        stdev=statistics.stdev(xs) if len(xs) > 1 else 0.0,
        median=statistics.median(xs),
        p90=xs[int(0.9 * (len(xs) - 1))],
        hit_rate=len(xs) / N_TRIALS if N_TRIALS else None,
    )

# --- LOO hyperparameter grid (small) on training collectors ---
GRID = [
    dict(same_sec=3.0, out_share=2.0, repeat=1.0, delegation=5.0, near_zero=2.0),  # a priori
    dict(same_sec=5.0, out_share=1.0, repeat=0.5, delegation=5.0, near_zero=3.0),
    dict(same_sec=1.0, out_share=4.0, repeat=2.0, delegation=2.0, near_zero=1.0),
    dict(same_sec=4.0, out_share=3.0, repeat=1.5, delegation=8.0, near_zero=4.0),
]

def score_W(W, train_pairs, trials=40):
    """Lower mean steps on weighted RW is better."""
    scores = []
    rng = random.Random(7)
    for seed, c, _ in train_pairs:
        hits = []
        for _ in range(trials):
            hits.append(random_walk(seed, c, True, W, max_steps=2000, rng=rng))
        sm = summarize.__wrapped__ if False else None
        xs = [h for h in hits if h is not None]
        if not xs: scores.append(1e9); continue
        scores.append(statistics.mean(xs))
    return statistics.mean(scores) if scores else 1e9

# Fix summarize for partial trials
def summarize_n(xs, n_trials):
    hit = [x for x in xs if x is not None]
    miss = n_trials - len(hit)
    if not hit:
        return dict(n_hit=0, n_miss=miss, mean=None, stdev=None, median=None, p90=None, hit_rate=0.0)
    hit = sorted(hit)
    return dict(
        n_hit=len(hit), n_miss=miss,
        mean=statistics.mean(hit),
        stdev=statistics.stdev(hit) if len(hit) > 1 else 0.0,
        median=statistics.median(hit),
        p90=hit[int(0.9 * (len(hit) - 1))],
        hit_rate=len(hit) / n_trials,
    )

results = {
    "graph": {
        "nodes": len(nodes),
        "edges": len(edges),
        "eth_edges": sum(1 for e in edges if e.get("chain") == "ethereum"),
        "base_edges": sum(1 for e in edges if e.get("chain") == "base"),
        "sol_edges": sum(1 for e in edges if e.get("chain") == "solana"),
        "seeds": SEEDS,
        "collectors_in_graph": [c for c in COLLECTORS_N if c in nodes],
        "reachable_pairs": [{"seed": s, "collector": c, "bfs_depth": d} for s, c, d in pairs],
        "base_note": G.get("base_note"),
    },
    "features_note": (
        "Features (same_sec, out_share, repeat, delegation, near_zero) are computed from "
        "transfer structure only — they do not read collector labels. Feature *choice* and "
        "DEFAULT_W were specified by the task / prior siphon observations (leakage of design). "
        "LOO tunes W on other collectors and tests on held-out collector."
    ),
    "default_W": DEFAULT_W,
    "per_collector": [],
    "loo": [],
}

# Per-collector evaluation with DEFAULT_W (a priori)
for seed, c, depth in pairs:
    bfs_ok, bfs_d, bfs_exp = bfs_expand(seed, c)
    gr_ok, gr_d, gr_exp = greedy_expand(seed, c, DEFAULT_W)
    bool_steps, rich_steps = [], []
    for i in range(N_TRIALS):
        rng = random.Random(1000 + i)
        bool_steps.append(random_walk(seed, c, False, DEFAULT_W, rng=rng))
        rng = random.Random(1000 + i)
        rich_steps.append(random_walk(seed, c, True, DEFAULT_W, rng=rng))
    entry = {
        "seed": seed, "collector": c, "bfs_depth": bfs_d,
        "boolean_bfs_nodes_expanded": bfs_exp,
        "rich_greedy_nodes_expanded": gr_exp if gr_ok else None,
        "rich_greedy_depth": gr_d,
        "boolean_rw": summarize_n(bool_steps, N_TRIALS),
        "rich_rw_defaultW": summarize_n(rich_steps, N_TRIALS),
    }
    # ratio (rich mean / bool mean); <1 means rich faster
    bm, rm = entry["boolean_rw"]["mean"], entry["rich_rw_defaultW"]["mean"]
    entry["rw_mean_ratio_rich_over_bool"] = (rm / bm) if (bm and rm) else None
    results["per_collector"].append(entry)

# Leave-one-collector-out
collectors_present = sorted({c for _, c, _ in pairs})
for held in collectors_present:
    train = [(s, c, d) for s, c, d in pairs if c != held]
    test = [(s, c, d) for s, c, d in pairs if c == held]
    if not train or not test: continue
    # pick best W on train
    best_W, best_score = DEFAULT_W, score_W(DEFAULT_W, train, trials=30)
    for W in GRID[1:]:
        sc = score_W(W, train, trials=30)
        if sc < best_score:
            best_W, best_score = W, sc
    loo_entries = []
    for seed, c, _ in test:
        bool_steps, rich_steps = [], []
        for i in range(N_TRIALS):
            rng = random.Random(2000 + i)
            bool_steps.append(random_walk(seed, c, False, best_W, rng=rng))
            rng = random.Random(2000 + i)
            rich_steps.append(random_walk(seed, c, True, best_W, rng=rng))
        be, re = summarize_n(bool_steps, N_TRIALS), summarize_n(rich_steps, N_TRIALS)
        loo_entries.append({
            "seed": seed, "collector": c,
            "boolean_rw": be, "rich_rw_looW": re,
            "rw_mean_ratio_rich_over_bool": (re["mean"] / be["mean"]) if (be["mean"] and re["mean"]) else None,
            "chosen_W": best_W, "train_score": best_score,
        })
    results["loo"].append({"held_out": held, "tests": loo_entries})

# Aggregate verdict
ratios = [e["rw_mean_ratio_rich_over_bool"] for e in results["per_collector"] if e["rw_mean_ratio_rich_over_bool"]]
loo_ratios = [t["rw_mean_ratio_rich_over_bool"] for L in results["loo"] for t in L["tests"] if t["rw_mean_ratio_rich_over_bool"]]
bfs_vs_greedy = []
for e in results["per_collector"]:
    if e["rich_greedy_nodes_expanded"] and e["boolean_bfs_nodes_expanded"]:
        bfs_vs_greedy.append(e["rich_greedy_nodes_expanded"] / e["boolean_bfs_nodes_expanded"])

def verdict(ratios):
    if not ratios: return "inconclusive", None
    m = statistics.mean(ratios)
    # win if rich clearly faster (ratio < 0.9), loss if > 1.1, else tie
    if m < 0.9: return "win", m
    if m > 1.1: return "loss", m
    return "tie", m

v_def, m_def = verdict(ratios)
v_loo, m_loo = verdict(loo_ratios)
v_exp, m_exp = verdict(bfs_vs_greedy)  # <1 means greedy expands fewer

results["aggregate"] = {
    "defaultW_rw_ratio_mean": m_def,
    "defaultW_verdict": v_def,
    "loo_rw_ratio_mean": m_loo,
    "loo_verdict": v_loo,
    "greedy_over_bfs_expand_ratio_mean": m_exp,
    "greedy_vs_bfs_verdict": v_exp,
    "n_reachable_pairs": len(pairs),
    "n_trials_per_pair": N_TRIALS,
}

out = ROOT / "results.json"
json.dump(results, open(out, "w"), indent=2)
print(json.dumps(results["aggregate"], indent=2))
print("pairs", len(pairs))
for e in results["per_collector"]:
    print(e["collector"][:12], "bfs", e["bfs_depth"], "bool", e["boolean_rw"]["mean"], "rich", e["rich_rw_defaultW"]["mean"], "ratio", e["rw_mean_ratio_rich_over_bool"], "exp", e["boolean_bfs_nodes_expanded"], "->", e["rich_greedy_nodes_expanded"])
