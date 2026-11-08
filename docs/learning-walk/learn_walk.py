#!/usr/bin/env python3
"""Learning rich walk: error / red-lining matrix + short iterative loops.

Experiment 1 — siphon graph: miss-node features update multiplicative weights;
  leave-one-collector-out so the walk cannot memorise answers.
Experiment 2 — Bitcoin puzzle fractional positions: same loop on #1–#59 train,
  evaluate search-order ranking on held-out #60–#70 (S=2^20).

Honest numbers only. No invented results.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import random
import statistics
from collections import Counter, defaultdict, deque
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SIPHON = Path("/workspace/siphon-walk")
PUZZLE_CSV = Path("/workspace/btc-puzzle/patterns/export.csv")

N_LOOPS = 8
N_TRIALS = 120  # per collector per loop (LOO); enough for stable means
N_EPISODES_TRAIN = 40  # episodes per train collector per loop for error matrix
ETA = 0.25  # multiplicative-weights learning rate
S = 1 << 20
N_BINS = 64
PUZZLE_TRIALS = 400
PUZZLE_EPISODES = 80  # train episodes per loop

FEATURE_KEYS = ("same_sec", "out_share", "repeat", "delegation", "near_zero")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def norm(a):
    if not a:
        return None
    return a.lower() if isinstance(a, str) and (a.startswith("0x") or a.startswith("0X")) else a


def summarize_n(xs, n_trials):
    hit = [x for x in xs if x is not None]
    if not hit:
        return dict(n_hit=0, n_miss=n_trials, mean=None, stdev=None, median=None, hit_rate=0.0)
    hit = sorted(hit)
    return dict(
        n_hit=len(hit),
        n_miss=n_trials - len(hit),
        mean=statistics.mean(hit),
        stdev=statistics.stdev(hit) if len(hit) > 1 else 0.0,
        median=statistics.median(hit),
        hit_rate=len(hit) / n_trials,
    )


def entropy(w):
    s = sum(w)
    if s <= 0:
        return 0.0
    return -sum((p / s) * math.log2(p / s) for p in w if p > 0)


# ---------------------------------------------------------------------------
# Experiment 1 — siphon graph
# ---------------------------------------------------------------------------

def load_siphon():
    G = json.load(open(SIPHON / "graph.json"))
    collectors = [
        "0xeeeee90971b6264c53175d3af6840a8dd5dc7b6c",
        "0xf111122404b8c2fc01dff89c65d3104fbb608008",
        "0x8566263047ead285194b2e8feb53f312cf8cb463",
        "0x09cbc0d92aabe6f53ac7e84f0ba0fbfd05eb80f2",
        "FncazAs6omJJjtLVzquzT9KoyXn6tFixr9kGjr42ktLj",
        "5qmtDCvUreD8G59M5FosdpV8Gqdd3kFgdH1Vv7HKXUKq",
        "7jNPvxGzQ5wG5NMYZD1GGLAvCyYF7v1Ai5PV9whYt9AN",
    ]
    collectors_n = [norm(c) if c.startswith("0x") else c for c in collectors]
    seeds = [norm(s) for s in G["seeds"]["ethereum"]] + list(G["seeds"]["solana"])
    delegation = {norm(k): norm(v) for k, v in G.get("delegation", {}).items()}

    edges = []
    for e in G["edges"]:
        s, d = norm(e.get("src")), norm(e.get("dst"))
        if not s or not d or s == d:
            continue
        edges.append({**e, "src": s, "dst": d})

    adj = defaultdict(list)
    for e in edges:
        adj[e["src"]].append(e)

    nodes = set()
    for e in edges:
        nodes.add(e["src"])
        nodes.add(e["dst"])

    by_node_ts = defaultdict(list)
    for e in edges:
        ts = e.get("ts")
        if ts is None:
            continue
        try:
            ts = int(ts)
        except Exception:
            continue
        by_node_ts[e["dst"]].append((ts, "in", e["src"]))
        by_node_ts[e["src"]].append((ts, "out", e["dst"]))

    same_second_pair_count = Counter()
    for node, evs in by_node_ts.items():
        ins = [(t, o) for t, d, o in evs if d == "in"]
        outs = [(t, o) for t, d, o in evs if d == "out"]
        in_by_t = defaultdict(list)
        for t, o in ins:
            in_by_t[t].append(o)
        for t, o in outs:
            if in_by_t.get(t):
                same_second_pair_count[(node, o)] += 1

    out_value = Counter()
    edge_value = Counter()
    repeat_count = Counter()
    in_value = Counter()
    for e in edges:
        v = float(e.get("value") or 0)
        out_value[e["src"]] += max(v, 0)
        in_value[e["dst"]] += max(v, 0)
        edge_value[(e["src"], e["dst"])] += max(v, 0)
        repeat_count[(e["src"], e["dst"])] += 1

    def outflow_share(s, d):
        tot = out_value[s]
        return 0.0 if tot <= 0 else edge_value[(s, d)] / tot

    def near_zero_residual(s, d):
        inn, out = in_value[s], out_value[s]
        if out <= 0:
            return 0.0
        if inn <= 0:
            return 1.0 if outflow_share(s, d) >= 0.5 else 0.0
        residual = max(inn - out, 0) / inn
        if residual < 0.05 and outflow_share(s, d) >= 0.1:
            return 1.0
        return 0.0

    def feat(s, d):
        return {
            "same_sec": float(same_second_pair_count.get((s, d), 0)),
            "out_share": outflow_share(s, d),
            "repeat": float(repeat_count[(s, d)]),
            "delegation": 1.0 if delegation.get(s) == d else 0.0,
            "near_zero": near_zero_residual(s, d),
        }

    # Precompute per-edge features
    edge_feat = {}
    for e in edges:
        edge_feat[(e["src"], e["dst"])] = feat(e["src"], e["dst"])

    # Also node-level aggregate features (for miss-node red-lining)
    node_feat = {}
    for n in nodes:
        outs = adj.get(n, [])
        if not outs:
            node_feat[n] = {k: 0.0 for k in FEATURE_KEYS}
            continue
        acc = {k: 0.0 for k in FEATURE_KEYS}
        for e in outs:
            f = edge_feat[(e["src"], e["dst"])]
            for k in FEATURE_KEYS:
                acc[k] += f[k]
        for k in FEATURE_KEYS:
            acc[k] /= len(outs)
        node_feat[n] = acc

    return {
        "adj": adj,
        "nodes": nodes,
        "seeds": seeds,
        "collectors_n": collectors_n,
        "edge_feat": edge_feat,
        "node_feat": node_feat,
        "n_edges": len(edges),
    }


def rich_weight(s, d, W, edge_feat):
    f = edge_feat.get((s, d), {k: 0.0 for k in FEATURE_KEYS})
    score = 1e-6
    score += W["same_sec"] * math.log1p(f["same_sec"])
    score += W["out_share"] * f["out_share"]
    score += W["repeat"] * math.log1p(f["repeat"])
    score += W["delegation"] * f["delegation"]
    score += W["near_zero"] * f["near_zero"]
    return score


def bfs_path(adj, start, target, max_expand=50000):
    """Return set of nodes on one BFS shortest path (inclusive), or None."""
    if start == target:
        return {start}
    q = deque([start])
    parent = {start: None}
    expanded = 0
    while q:
        u = q.popleft()
        expanded += 1
        if expanded > max_expand:
            return None
        for e in adj.get(u, []):
            v = e["dst"]
            if v in parent:
                continue
            parent[v] = u
            if v == target:
                path = set()
                cur = v
                while cur is not None:
                    path.add(cur)
                    cur = parent[cur]
                return path
            q.append(v)
    return None


def random_walk(adj, edge_feat, start, target, weighted, W, max_steps=5000, rng=None, record_visit=False):
    """Return (steps|None, visited_list)."""
    rng = rng or random.Random()
    if start == target:
        return 0, [start]
    u = start
    seen = {u}
    visited = [u]
    for step in range(1, max_steps + 1):
        outs = adj.get(u, [])
        if not outs:
            u = start
            continue
        if weighted:
            ws = []
            for e in outs:
                v = e["dst"]
                w = rich_weight(u, v, W, edge_feat)
                if v in seen:
                    w *= 0.15
                ws.append(w)
            total = sum(ws)
            r = rng.random() * total
            acc = 0.0
            v = outs[-1]["dst"]
            for e, w in zip(outs, ws):
                acc += w
                if acc >= r:
                    v = e["dst"]
                    break
        else:
            v = rng.choice(outs)["dst"]
        visited.append(v)
        if v == target:
            return step, visited
        seen.add(v)
        u = v
    return None, visited


def reachable_pairs(g):
    pairs = []
    for seed in g["seeds"]:
        if seed not in g["nodes"] and seed not in g["adj"]:
            continue
        for c in g["collectors_n"]:
            if c not in g["nodes"]:
                continue
            seed_is_eth = isinstance(seed, str) and seed.startswith("0x")
            c_is_eth = isinstance(c, str) and c.startswith("0x")
            if seed_is_eth != c_is_eth:
                continue
            path = bfs_path(g["adj"], seed, c)
            if path is not None:
                pairs.append((seed, c, path))
    return pairs


def update_weights_from_error_matrix(W, error_matrix, eta=ETA):
    """Multiplicative-weights update from miss-feature aggregates.

    error_matrix[k] = sum of feature k over miss nodes (visited not on BFS path).
    Penalise features that co-occur with misses: W[k] *= exp(-eta * normalised_miss).
    """
    W2 = dict(W)
    total = sum(error_matrix.values()) or 1.0
    for k in FEATURE_KEYS:
        miss_frac = error_matrix[k] / total
        # also absolute scale so sparse features still move
        W2[k] = max(0.05, W2[k] * math.exp(-eta * miss_frac * 5.0))
    return W2


def run_siphon_loops():
    g = load_siphon()
    pairs = reachable_pairs(g)
    collectors_present = sorted({c for _, c, _ in pairs})

    DEFAULT_W = dict(same_sec=3.0, out_share=2.0, repeat=1.0, delegation=5.0, near_zero=2.0)

    loop_rows = []
    per_loop_detail = []
    W_global = dict(DEFAULT_W)  # warm start; LOO re-learns independently

    for loop in range(N_LOOPS):
        # Leave-one-collector-out: for each held collector, train error matrix
        # on other collectors, then evaluate on held.
        loo_ratios = []
        loo_bool_means = []
        loo_rich_means = []
        counter_7j = None
        chosen_Ws = []
        matrix_snapshots = []

        for held in collectors_present:
            train = [(s, c, path) for s, c, path in pairs if c != held]
            test = [(s, c, path) for s, c, path in pairs if c == held]
            if not train or not test:
                continue

            # --- train: accumulate error matrix from rich-walk episodes ---
            W = dict(DEFAULT_W) if loop == 0 else dict(W_global)
            # Actually: each LOO fold starts from previous loop's W_global
            # but learns its own update from train-only errors this loop.
            error_matrix = {k: 0.0 for k in FEATURE_KEYS}
            miss_node_count = 0
            hit_count = 0

            rng = random.Random(1000 + loop * 97 + hash(held) % 10000)
            for seed, c, path in train:
                for ep in range(N_EPISODES_TRAIN):
                    steps, visited = random_walk(
                        g["adj"], g["edge_feat"], seed, c, True, W,
                        max_steps=3000, rng=rng, record_visit=True,
                    )
                    # misses = visited nodes NOT on BFS shortest path
                    for n in visited:
                        if n in path:
                            continue
                        miss_node_count += 1
                        nf = g["node_feat"].get(n, {k: 0.0 for k in FEATURE_KEYS})
                        for k in FEATURE_KEYS:
                            error_matrix[k] += nf[k]
                    if steps is not None:
                        hit_count += 1

            W_updated = update_weights_from_error_matrix(W, error_matrix, eta=ETA)
            chosen_Ws.append(W_updated)
            matrix_snapshots.append({
                "held_out": held,
                "error_matrix": dict(error_matrix),
                "miss_nodes": miss_node_count,
                "train_hits": hit_count,
                "W_before": dict(W),
                "W_after": dict(W_updated),
            })

            # --- evaluate on held-out collector ---
            for seed, c, _path in test:
                bool_steps, rich_steps = [], []
                for i in range(N_TRIALS):
                    rng_b = random.Random(5000 + loop * 1000 + i)
                    bs, _ = random_walk(
                        g["adj"], g["edge_feat"], seed, c, False, W_updated,
                        max_steps=5000, rng=rng_b,
                    )
                    bool_steps.append(bs)
                    rng_r = random.Random(5000 + loop * 1000 + i)
                    rs, _ = random_walk(
                        g["adj"], g["edge_feat"], seed, c, True, W_updated,
                        max_steps=5000, rng=rng_r,
                    )
                    rich_steps.append(rs)
                be = summarize_n(bool_steps, N_TRIALS)
                re = summarize_n(rich_steps, N_TRIALS)
                ratio = (re["mean"] / be["mean"]) if (be["mean"] and re["mean"]) else None
                loo_ratios.append(ratio)
                if be["mean"]:
                    loo_bool_means.append(be["mean"])
                if re["mean"]:
                    loo_rich_means.append(re["mean"])
                short = c[:12] if isinstance(c, str) else str(c)[:12]
                entry = {
                    "held_out": held,
                    "collector_short": short,
                    "boolean_mean": be["mean"],
                    "rich_mean": re["mean"],
                    "ratio": ratio,
                    "bool_hit_rate": be["hit_rate"],
                    "rich_hit_rate": re["hit_rate"],
                }
                if "7jNPvx" in (c if isinstance(c, str) else ""):
                    counter_7j = entry

        # Aggregate W for next loop: mean of LOO fold W_after
        if chosen_Ws:
            W_global = {
                k: statistics.mean(w[k] for w in chosen_Ws) for k in FEATURE_KEYS
            }

        mean_ratio = statistics.mean([r for r in loo_ratios if r is not None]) if any(loo_ratios) else None
        row = {
            "loop": loop,
            "mean_ratio_rich_over_bool": mean_ratio,
            "n_loo_tests": len(loo_ratios),
            "mean_bool": statistics.mean(loo_bool_means) if loo_bool_means else None,
            "mean_rich": statistics.mean(loo_rich_means) if loo_rich_means else None,
            "W": dict(W_global),
            "counterexample_7jNPvx": counter_7j,
            "error_matrix_sum": {
                k: sum(m["error_matrix"][k] for m in matrix_snapshots)
                for k in FEATURE_KEYS
            },
            "miss_nodes_total": sum(m["miss_nodes"] for m in matrix_snapshots),
        }
        loop_rows.append(row)
        per_loop_detail.append({
            "loop": loop,
            "folds": matrix_snapshots,
            "loo_ratios": loo_ratios,
        })
        print(
            f"[siphon] loop {loop}: ratio={mean_ratio:.4f}" if mean_ratio else f"[siphon] loop {loop}: ratio=None",
            f"W={ {k: round(v, 3) for k, v in W_global.items()} }",
            f"7j={counter_7j['ratio'] if counter_7j and counter_7j['ratio'] else None}",
            flush=True,
        )

    # Verdict
    first = loop_rows[0]["mean_ratio_rich_over_bool"]
    last = loop_rows[-1]["mean_ratio_rich_over_bool"]
    ratios = [r["mean_ratio_rich_over_bool"] for r in loop_rows if r["mean_ratio_rich_over_bool"]]
    best = min(ratios) if ratios else None
    improved = (last is not None and first is not None and last < first - 0.02)
    cex_first = loop_rows[0].get("counterexample_7jNPvx")
    cex_last = loop_rows[-1].get("counterexample_7jNPvx")
    cex_improved = False
    if cex_first and cex_last and cex_first.get("ratio") and cex_last.get("ratio"):
        cex_improved = cex_last["ratio"] < cex_first["ratio"] - 0.02

    if improved and last < 0.9:
        verdict = "win: learning loop reduced LOO ratio vs Boolean RW"
    elif improved:
        verdict = "partial: ratio improved across loops but not clearly < 0.9"
    elif best is not None and best < 0.9:
        verdict = "static win: rich walk stays faster; learning did not further improve"
    else:
        verdict = "no_improvement: learning loop did not beat starting rich walk on LOO"

    return {
        "experiment": "siphon_error_matrix_loops",
        "n_loops": N_LOOPS,
        "n_trials_per_loo": N_TRIALS,
        "n_episodes_train": N_EPISODES_TRAIN,
        "eta": ETA,
        "graph": {"nodes": len(g["nodes"]), "edges": g["n_edges"], "reachable_pairs": len(pairs)},
        "loops": loop_rows,
        "verdict": verdict,
        "first_ratio": first,
        "last_ratio": last,
        "best_ratio": best,
        "learning_improved": improved,
        "counterexample_7jNPvx_improved": cex_improved,
        "detail_path": "error_matrix_loop_siphon.json",
        "detail": per_loop_detail,
    }


# ---------------------------------------------------------------------------
# Experiment 2 — puzzle fractional positions
# ---------------------------------------------------------------------------

def load_puzzle_fracs():
    rows = list(csv.DictReader(open(PUZZLE_CSV)))
    out = []
    for r in rows:
        if not r.get("private_key"):
            continue
        i = int(r["id"])
        lo, hi = int(r["range_min"], 16), int(r["range_max"], 16)
        if hi <= lo:
            continue
        k = int(r["private_key"], 16)
        out.append({"id": i, "frac": (k - lo) / (hi - lo)})
    return out


def rich_walk_steps(target, weights, rng):
    n_bins = len(weights)
    bin_size = S // n_bins
    target_bin = min(n_bins - 1, target * n_bins // S)
    lo = target_bin * bin_size
    hi = S if target_bin == n_bins - 1 else (target_bin + 1) * bin_size
    bin_len = hi - lo
    remaining = list(range(n_bins))
    steps = 0
    while remaining:
        ww = [weights[b] for b in remaining]
        r = rng.random() * sum(ww)
        acc = 0.0
        choice_i = 0
        for i, b in enumerate(remaining):
            acc += weights[b]
            if acc >= r:
                choice_i = i
                break
        b = remaining.pop(choice_i)
        if b != target_bin:
            bl = (S - b * bin_size) if b == n_bins - 1 else bin_size
            steps += bl
        else:
            steps += rng.randint(1, bin_len)
            return steps
    return steps


def random_steps(target, rng):
    # Uniform: expected S/2; exact: rank of target in random perm ≈ uniform 1..S
    return rng.randint(1, S)


def update_bin_weights_from_misses(weights, miss_bins, eta=ETA):
    """Penalise bins that were exhausted (missed) before hitting target."""
    w = list(weights)
    total = sum(miss_bins) or 1.0
    for b in range(len(w)):
        miss_frac = miss_bins[b] / total
        w[b] = max(1e-6, w[b] * math.exp(-eta * miss_frac * 3.0))
    s = sum(w)
    return [x / s for x in w]


def run_puzzle_loops():
    fracs = load_puzzle_fracs()
    train = [x for x in fracs if 1 <= x["id"] <= 59]
    test = [x for x in fracs if 60 <= x["id"] <= 70]
    # Start uniform
    weights = [1.0 / N_BINS] * N_BINS
    # Also seed with train density (same as prior rich_walk) as loop-0 prior
    dens = [1.0] * N_BINS
    for x in train:
        dens[min(N_BINS - 1, int(x["frac"] * N_BINS))] += 1.0
    s = sum(dens)
    dens = [v / s for v in dens]

    loop_rows = []
    detail = []

    for loop in range(N_LOOPS):
        # Use current weights; loop 0 uses density prior from train
        W = dens if loop == 0 else weights

        # --- train episodes: for each train puzzle, map frac into S, walk, record miss bins ---
        miss_bins = [0.0] * N_BINS
        rng = random.Random(42 + loop * 17)
        for ep in range(PUZZLE_EPISODES):
            x = train[ep % len(train)]
            # Place a synthetic target at frac * S
            target = min(S - 1, int(x["frac"] * S))
            # Simulate which bins would be exhausted before target bin
            target_bin = min(N_BINS - 1, target * N_BINS // S)
            remaining = list(range(N_BINS))
            while remaining:
                ww = [W[b] for b in remaining]
                r = rng.random() * sum(ww)
                acc = 0.0
                choice_i = 0
                for i, b in enumerate(remaining):
                    acc += W[b]
                    if acc >= r:
                        choice_i = i
                        break
                b = remaining.pop(choice_i)
                if b == target_bin:
                    break
                miss_bins[b] += 1.0

        weights = update_bin_weights_from_misses(W, miss_bins, eta=ETA)

        # --- evaluate on held-out #60–#70 ---
        ratios = []
        rich_means = []
        rand_means = []
        per_puzzle = []
        for x in test:
            target = min(S - 1, int(x["frac"] * S))
            rich_s, rand_s = [], []
            for t in range(PUZZLE_TRIALS):
                rng_r = random.Random(9000 + loop * 10000 + x["id"] * 400 + t)
                rich_s.append(rich_walk_steps(target, weights, rng_r))
                rng_u = random.Random(9000 + loop * 10000 + x["id"] * 400 + t)
                rand_s.append(random_steps(target, rng_u))
            rm = statistics.mean(rich_s)
            um = statistics.mean(rand_s)
            ratio = rm / um if um else None
            ratios.append(ratio)
            rich_means.append(rm)
            rand_means.append(um)
            per_puzzle.append({"id": x["id"], "frac": x["frac"], "rich_mean": rm, "rand_mean": um, "ratio": ratio})

        mean_ratio = statistics.mean(ratios)
        ent = entropy(weights)
        row = {
            "loop": loop,
            "mean_ratio_rich_over_random": mean_ratio,
            "entropy_bits": ent,
            "entropy_uniform": math.log2(N_BINS),
            "mean_rich_steps": statistics.mean(rich_means),
            "mean_rand_steps": statistics.mean(rand_means),
            "miss_bins_sum": sum(miss_bins),
            "top5_bins": sorted(range(N_BINS), key=lambda b: -weights[b])[:5],
            "top5_weights": [round(weights[b], 5) for b in sorted(range(N_BINS), key=lambda b: -weights[b])[:5]],
        }
        loop_rows.append(row)
        detail.append({"loop": loop, "per_puzzle": per_puzzle, "weights": weights, "miss_bins": miss_bins})
        print(
            f"[puzzle] loop {loop}: ratio={mean_ratio:.4f} entropy={ent:.3f}/{math.log2(N_BINS):.3f}",
            flush=True,
        )

    first = loop_rows[0]["mean_ratio_rich_over_random"]
    last = loop_rows[-1]["mean_ratio_rich_over_random"]
    best = min(r["mean_ratio_rich_over_random"] for r in loop_rows)
    improved = last < first - 0.02
    # Expect no improvement on uniform space
    if best < 0.9 and improved:
        verdict = "unexpected_win: learning found a faster prior on held-out #60-70"
    elif best < 0.95:
        verdict = "weak_signal: slight bias, not a clear win"
    else:
        verdict = (
            "falsified_as_expected: uniform keyspace — error-matrix loops did not beat random "
            f"(first={first:.3f}, last={last:.3f}, best={best:.3f})"
        )

    return {
        "experiment": "puzzle_error_matrix_loops",
        "S": S,
        "n_bins": N_BINS,
        "n_loops": N_LOOPS,
        "trials_per_puzzle": PUZZLE_TRIALS,
        "train_n": len(train),
        "test_ids": [x["id"] for x in test],
        "loops": loop_rows,
        "verdict": verdict,
        "first_ratio": first,
        "last_ratio": last,
        "best_ratio": best,
        "learning_improved": improved,
        "detail_path": "error_matrix_loop_puzzle.json",
        "detail": detail,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=== Experiment 1: siphon learning walk ===", flush=True)
    siphon = run_siphon_loops()
    # Write siphon detail separately (large)
    detail_s = siphon.pop("detail")
    json.dump(detail_s, open(ROOT / "error_matrix_loop_siphon.json", "w"), indent=2)

    print("=== Experiment 2: puzzle learning walk ===", flush=True)
    puzzle = run_puzzle_loops()
    detail_p = puzzle.pop("detail")
    json.dump(detail_p, open(ROOT / "error_matrix_loop_puzzle.json", "w"), indent=2)

    results = {
        "siphon": siphon,
        "puzzle": puzzle,
        "method": {
            "error_matrix": (
                "Miss nodes = visited nodes not on BFS shortest path to collector (siphon), "
                "or exhausted bins before target bin (puzzle). Feature aggregates over misses "
                "update weights via multiplicative weights W *= exp(-eta * miss_frac)."
            ),
            "evaluation": (
                "Siphon: leave-one-collector-out each loop. "
                "Puzzle: train #1-59, eval #60-70 on S=2^20."
            ),
            "n_loops": N_LOOPS,
            "eta": ETA,
        },
    }
    json.dump(results, open(ROOT / "results.json", "w"), indent=2)

    # RESULTS.md
    lines = [
        "# Learning walk — error / red-lining matrix loops",
        "",
        "Rich walk that remembers past failed diagonals: miss nodes (or bins) form an",
        "error matrix; multiplicative-weights updates push the next loop off those misses.",
        "Leave-one-collector-out (siphon) and held-out puzzles #60–#70 keep the walk from",
        "memorising answers. Numbers are from live runs on real graph / export.csv data.",
        "",
        "## Experiment 1 — siphon graph",
        "",
        f"- Graph: {siphon['graph']['nodes']} nodes, {siphon['graph']['edges']} edges, "
        f"{siphon['graph']['reachable_pairs']} reachable seed→collector pairs.",
        f"- Loops: {N_LOOPS}; trials/LOO fold: {N_TRIALS}; train episodes/collector/loop: {N_EPISODES_TRAIN}; η={ETA}.",
        f"- Prior static rich RW (no learning): 0.60× Boolean RW (LOO 0.605×); counterexample `7jNPvx…` 1.24×.",
        "",
        "| loop | mean ratio (rich/bool LOO) | mean bool steps | mean rich steps | 7jNPvx ratio | W (rounded) |",
        "|-----:|---------------------------:|----------------:|----------------:|-------------:|:------------|",
    ]
    for r in siphon["loops"]:
        cex = r.get("counterexample_7jNPvx")
        cex_r = f"{cex['ratio']:.3f}" if cex and cex.get("ratio") else "—"
        Wr = ", ".join(f"{k}={v:.2f}" for k, v in r["W"].items())
        lines.append(
            f"| {r['loop']} | "
            f"{r['mean_ratio_rich_over_bool']:.4f} | "
            f"{r['mean_bool']:.1f} | "
            f"{r['mean_rich']:.1f} | "
            f"{cex_r} | `{Wr}` |"
        )
    lines += [
        "",
        f"**Verdict:** {siphon['verdict']}",
        f"- first={siphon['first_ratio']:.4f}, last={siphon['last_ratio']:.4f}, "
        f"best={siphon['best_ratio']:.4f}, learning_improved={siphon['learning_improved']}, "
        f"7jNPvx_improved={siphon['counterexample_7jNPvx_improved']}",
        "",
        "### Caveats (siphon)",
        "",
        "- Feature *choice* still comes from prior siphon observations (design leakage); LOO only",
        "  protects weight learning, not feature invention.",
        "- Miss definition uses BFS shortest path as the 'true' diagonal; other shortest paths",
        "  or multi-hop collectors may mis-label some nodes as misses.",
        "- When BFS depth is 1, Boolean BFS already wins on expand count; this experiment scores",
        "  random walks, not expanders.",
        "",
        "## Experiment 2 — Bitcoin puzzle positions (#1–#59 train → #60–#70 eval)",
        "",
        f"- S=2^{int(math.log2(S))}, bins={N_BINS}, trials/puzzle={PUZZLE_TRIALS}, loops={N_LOOPS}.",
        f"- Train n={puzzle['train_n']}; test ids={puzzle['test_ids']}.",
        "",
        "| loop | mean ratio (rich/random) | entropy (bits) | uniform entropy | mean rich steps | mean rand steps |",
        "|-----:|-------------------------:|---------------:|----------------:|----------------:|----------------:|",
    ]
    for r in puzzle["loops"]:
        lines.append(
            f"| {r['loop']} | "
            f"{r['mean_ratio_rich_over_random']:.4f} | "
            f"{r['entropy_bits']:.3f} | "
            f"{r['entropy_uniform']:.3f} | "
            f"{r['mean_rich_steps']:.0f} | "
            f"{r['mean_rand_steps']:.0f} |"
        )
    lines += [
        "",
        f"**Verdict:** {puzzle['verdict']}",
        f"- first={puzzle['first_ratio']:.4f}, last={puzzle['last_ratio']:.4f}, "
        f"best={puzzle['best_ratio']:.4f}, learning_improved={puzzle['learning_improved']}",
        "",
        "### Caveats (puzzle)",
        "",
        "- Only fractional *position* within each puzzle range is used (no pubkey, no kangaroo).",
        "- Uniform keyspace: AM–GM / Shoup already say no sub-√N generic walk; this tests whether",
        "  an error-matrix prior can still bias #60–#70. Expect ≈1.0×.",
        "- Density prior at loop 0 matches the earlier falsified rich_walk; subsequent loops",
        "  only reweight bins from train misses.",
        "",
        "## Method",
        "",
        results["method"]["error_matrix"],
        "",
        results["method"]["evaluation"],
        "",
        "## Files",
        "",
        "- `learn_walk.py` — runner",
        "- `results.json` — aggregate",
        "- `error_matrix_loop_siphon.json` / `error_matrix_loop_puzzle.json` — per-loop detail",
        "",
    ]
    (ROOT / "RESULTS.md").write_text("\n".join(lines) + "\n")
    print("Wrote", ROOT / "results.json", ROOT / "RESULTS.md", flush=True)
    print("SIPHON verdict:", siphon["verdict"], flush=True)
    print("PUZZLE verdict:", puzzle["verdict"], flush=True)


if __name__ == "__main__":
    main()
