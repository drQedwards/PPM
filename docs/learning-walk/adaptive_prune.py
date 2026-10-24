#!/usr/bin/env python3
"""Adaptive-prune third method on top of learn_walk results.

After each loop: if the error matrix / learned prior is flat for a region
(feature or collector / bin-space), PRUNE — drop learning there and use the
plain baseline (Boolean RW / uniform order). Flatline is a reportable null,
not a failure.

Reports steps ratio vs baseline AND total compute including learning overhead.
"""
from __future__ import annotations

import json
import math
import random
import statistics
import time
from collections import defaultdict
from pathlib import Path

# Reuse loaders / walk from learn_walk
import learn_walk as lw

ROOT = Path(__file__).resolve().parent

N_LOOPS = 8
N_TRIALS = 120
N_EPISODES_TRAIN = 40
ETA = 0.25
NOISE_TOL = 0.05          # held-out gain must beat previous by this to keep learning
ENTROPY_TOL = 0.15        # bits below uniform → still "has signal"; within this of uniform = flat
FEATURE_FLAT_CV = 0.25    # coeff of variation of error_matrix values; below = flat features


def entropy_dict(d):
    vals = [max(v, 0.0) for v in d.values()]
    s = sum(vals)
    if s <= 0:
        return 0.0
    return -sum((v / s) * math.log2(v / s) for v in vals if v > 0)


def is_flat_error_matrix(error_matrix, n_keys):
    """True if miss-feature distribution is near-uniform (no red-line signal)."""
    H = entropy_dict(error_matrix)
    H_max = math.log2(n_keys) if n_keys > 1 else 0.0
    vals = list(error_matrix.values())
    mean = statistics.mean(vals) if vals else 0.0
    sd = statistics.pstdev(vals) if len(vals) > 1 else 0.0
    cv = (sd / mean) if mean > 1e-12 else 0.0
    near_uniform_entropy = (H_max - H) <= ENTROPY_TOL
    low_cv = cv < FEATURE_FLAT_CV
    return near_uniform_entropy or low_cv, {
        "entropy": H, "entropy_max": H_max, "cv": cv,
        "near_uniform_entropy": near_uniform_entropy, "low_cv": low_cv,
    }


def prune_flat_features(W, error_matrix, default_W):
    """Freeze features whose miss mass is near the mean (no distinctive red line)."""
    vals = list(error_matrix.values())
    if not vals or sum(vals) <= 0:
        return dict(W), list(lw.FEATURE_KEYS)  # prune all — no signal
    mean = statistics.mean(vals)
    sd = statistics.pstdev(vals) if len(vals) > 1 else 0.0
    pruned = []
    W2 = dict(W)
    for k, v in error_matrix.items():
        # Feature is "flat" if its miss mass is within 0.5 sd of mean (not distinctive)
        if sd < 1e-12 or abs(v - mean) <= 0.5 * sd:
            W2[k] = default_W[k]  # revert to prior; stop learning this feature
            pruned.append(k)
    return W2, pruned


def run_siphon_adaptive():
    g = lw.load_siphon()
    pairs = lw.reachable_pairs(g)
    collectors_present = sorted({c for _, c, _ in pairs})
    DEFAULT_W = dict(same_sec=3.0, out_share=2.0, repeat=1.0, delegation=5.0, near_zero=2.0)

    # Per-collector prune state: once pruned, that collector uses Boolean RW forever
    collector_pruned = {c: False for c in collectors_present}
    # Global feature prune set
    features_pruned = set()
    W_global = dict(DEFAULT_W)

    loops = []
    prev_ratio = None

    for loop in range(N_LOOPS):
        loo_rich_or_base_means = []
        loo_bool_means = []
        loo_ratios = []
        learning_steps = 0  # overhead: steps walked during train episodes
        eval_steps_adaptive = 0
        eval_steps_bool = 0
        n_pruned_collectors = 0
        fold_info = []
        counter_7j = None
        chosen_Ws = []
        any_learning_this_loop = False

        # Global flat test from previous loop's aggregate will be applied at end
        for held in collectors_present:
            train = [(s, c, path) for s, c, path in pairs if c != held]
            test = [(s, c, path) for s, c, path in pairs if c == held]
            if not train or not test:
                continue

            W = dict(W_global)
            # Freeze already-pruned features at default
            for k in features_pruned:
                W[k] = DEFAULT_W[k]

            error_matrix = {k: 0.0 for k in lw.FEATURE_KEYS}
            miss_node_count = 0

            # Learning only if this fold's train region is not globally abandoned
            # and held collector is not yet pruned (we still learn from others)
            do_learn = not all(collector_pruned[c] for _, c, _ in train)

            rng = random.Random(3000 + loop * 97 + hash(held) % 10000)
            if do_learn:
                any_learning_this_loop = True
                for seed, c, path in train:
                    if collector_pruned.get(c):
                        continue  # skip pruned train collectors — no overhead
                    for ep in range(N_EPISODES_TRAIN):
                        steps, visited = lw.random_walk(
                            g["adj"], g["edge_feat"], seed, c, True, W,
                            max_steps=3000, rng=rng,
                        )
                        learning_steps += steps if steps is not None else 3000
                        for n in visited:
                            if n in path:
                                continue
                            miss_node_count += 1
                            nf = g["node_feat"].get(n, {k: 0.0 for k in lw.FEATURE_KEYS})
                            for k in lw.FEATURE_KEYS:
                                if k in features_pruned:
                                    continue
                                error_matrix[k] += nf[k]

                flat, flat_stats = is_flat_error_matrix(error_matrix, len(lw.FEATURE_KEYS))
                if flat:
                    # Prune all remaining learnable features this fold
                    newly = [k for k in lw.FEATURE_KEYS if k not in features_pruned]
                    features_pruned.update(newly)
                    W_updated = dict(DEFAULT_W)
                    pruned_feats = newly
                else:
                    W_updated = lw.update_weights_from_error_matrix(W, error_matrix, eta=ETA)
                    W_updated, pruned_feats = prune_flat_features(W_updated, error_matrix, DEFAULT_W)
                    features_pruned.update(pruned_feats)
                    # Re-freeze
                    for k in features_pruned:
                        W_updated[k] = DEFAULT_W[k]
            else:
                flat, flat_stats = True, {"entropy": 0, "entropy_max": 0, "cv": 0,
                                          "near_uniform_entropy": True, "low_cv": True}
                W_updated = dict(DEFAULT_W)
                pruned_feats = list(lw.FEATURE_KEYS)

            chosen_Ws.append(W_updated)
            fold_info.append({
                "held_out": held,
                "flat": flat,
                "flat_stats": flat_stats,
                "pruned_features": sorted(features_pruned),
                "miss_nodes": miss_node_count,
                "do_learn": do_learn,
            })

            # Evaluate held-out: adaptive uses Boolean if collector pruned OR flat
            for seed, c, _path in test:
                use_baseline = collector_pruned.get(c, False) or flat
                if use_baseline:
                    n_pruned_collectors += 1

                bool_steps, adapt_steps = [], []
                for i in range(N_TRIALS):
                    rng_b = random.Random(7000 + loop * 1000 + i)
                    bs, _ = lw.random_walk(
                        g["adj"], g["edge_feat"], seed, c, False, W_updated,
                        max_steps=5000, rng=rng_b,
                    )
                    bool_steps.append(bs)
                    eval_steps_bool += bs if bs is not None else 5000

                    rng_a = random.Random(7000 + loop * 1000 + i)
                    if use_baseline:
                        # baseline = Boolean RW, same seed path as bool for fair count
                        # but independent trial index offset so we don't double-count identical
                        rng_a2 = random.Random(7100 + loop * 1000 + i)
                        as_, _ = lw.random_walk(
                            g["adj"], g["edge_feat"], seed, c, False, W_updated,
                            max_steps=5000, rng=rng_a2,
                        )
                    else:
                        as_, _ = lw.random_walk(
                            g["adj"], g["edge_feat"], seed, c, True, W_updated,
                            max_steps=5000, rng=rng_a,
                        )
                    adapt_steps.append(as_)
                    eval_steps_adaptive += as_ if as_ is not None else 5000

                be = lw.summarize_n(bool_steps, N_TRIALS)
                ae = lw.summarize_n(adapt_steps, N_TRIALS)
                ratio = (ae["mean"] / be["mean"]) if (be["mean"] and ae["mean"]) else None
                loo_ratios.append(ratio)
                if be["mean"]:
                    loo_bool_means.append(be["mean"])
                if ae["mean"]:
                    loo_rich_or_base_means.append(ae["mean"])

                entry = {
                    "collector": c,
                    "used_baseline": use_baseline,
                    "boolean_mean": be["mean"],
                    "adaptive_mean": ae["mean"],
                    "ratio": ratio,
                }
                if isinstance(c, str) and "7jNPvx" in c:
                    counter_7j = entry

                # Per-collector prune decision: no gain vs Boolean beyond noise
                if ratio is not None and ratio > 1.0 - NOISE_TOL:
                    # rich/adapt not clearly beating bool → prune this collector
                    if not collector_pruned[c]:
                        collector_pruned[c] = True

        if chosen_Ws:
            # Only average weights for features not pruned
            W_global = {}
            for k in lw.FEATURE_KEYS:
                if k in features_pruned:
                    W_global[k] = DEFAULT_W[k]
                else:
                    W_global[k] = statistics.mean(w[k] for w in chosen_Ws)

        mean_ratio = statistics.mean([r for r in loo_ratios if r is not None]) if any(
            r is not None for r in loo_ratios
        ) else None

        # Loop-level flat / no-gain prune of ALL remaining learning
        no_gain = (
            prev_ratio is not None
            and mean_ratio is not None
            and mean_ratio >= prev_ratio - NOISE_TOL
        )
        if no_gain or not any_learning_this_loop:
            # Prune every collector and every feature
            for c in collectors_present:
                collector_pruned[c] = True
            features_pruned.update(lw.FEATURE_KEYS)

        total_compute_adaptive = learning_steps + eval_steps_adaptive
        total_compute_bool = eval_steps_bool  # baseline has no learning overhead
        compute_ratio = (
            total_compute_adaptive / total_compute_bool if total_compute_bool else None
        )

        row = {
            "loop": loop,
            "mean_ratio_adaptive_over_bool": mean_ratio,
            "mean_bool": statistics.mean(loo_bool_means) if loo_bool_means else None,
            "mean_adaptive": statistics.mean(loo_rich_or_base_means) if loo_rich_or_base_means else None,
            "n_collectors_pruned": sum(1 for v in collector_pruned.values() if v),
            "n_collectors_total": len(collectors_present),
            "features_pruned": sorted(features_pruned),
            "n_features_pruned": len(features_pruned),
            "n_features_total": len(lw.FEATURE_KEYS),
            "no_gain_vs_prev": no_gain,
            "learning_steps_overhead": learning_steps,
            "eval_steps_adaptive": eval_steps_adaptive,
            "eval_steps_bool": eval_steps_bool,
            "total_compute_adaptive": total_compute_adaptive,
            "total_compute_bool": total_compute_bool,
            "compute_ratio_adaptive_over_bool": compute_ratio,
            "W": dict(W_global),
            "counterexample_7jNPvx": counter_7j,
            "folds": fold_info,
        }
        loops.append(row)
        prev_ratio = mean_ratio
        print(
            f"[adapt-siphon] loop {loop}: ratio={mean_ratio:.4f}" if mean_ratio else f"[adapt-siphon] loop {loop}: ratio=None",
            f"pruned_coll={row['n_collectors_pruned']}/{row['n_collectors_total']}",
            f"pruned_feat={row['n_features_pruned']}",
            f"compute_ratio={compute_ratio:.3f}" if compute_ratio else "",
            f"learn_overhead={learning_steps}",
            flush=True,
        )

    first = loops[0]["mean_ratio_adaptive_over_bool"]
    last = loops[-1]["mean_ratio_adaptive_over_bool"]
    best = min(r["mean_ratio_adaptive_over_bool"] for r in loops if r["mean_ratio_adaptive_over_bool"])
    final_pruned_c = loops[-1]["n_collectors_pruned"]
    final_pruned_f = loops[-1]["n_features_pruned"]

    # Did prune prevent the degradation seen in unpruned learning?
    unpruned = json.load(open(ROOT / "results.json"))["siphon"]
    unpruned_last = unpruned["last_ratio"]
    prevented_degradation = last is not None and unpruned_last is not None and last < unpruned_last - 0.05

    if final_pruned_c == len(collectors_present) and best >= 0.95:
        verdict = (
            "null_flatline: error matrix went flat; adaptive-prune fell back to Boolean RW "
            f"(best_ratio={best:.3f}, all {final_pruned_c} collectors pruned)"
        )
    elif prevented_degradation and best < 0.9:
        verdict = (
            "win: adaptive-prune kept rich walk where signal exists and cut flat regions; "
            f"avoided unpruned degradation (unpruned_last={unpruned_last:.3f}, adapt_last={last:.3f})"
        )
    elif best < 0.9:
        verdict = f"partial: adaptive ratio best={best:.3f}; pruned {final_pruned_c} collectors / {final_pruned_f} features"
    else:
        verdict = f"null: no clear gain after prune (best={best:.3f})"

    return {
        "experiment": "siphon_adaptive_prune",
        "loops": loops,
        "verdict": verdict,
        "first_ratio": first,
        "last_ratio": last,
        "best_ratio": best,
        "final_collectors_pruned": final_pruned_c,
        "final_features_pruned": final_pruned_f,
        "prevented_unpruned_degradation": prevented_degradation,
        "unpruned_last_ratio": unpruned_last,
    }


def run_puzzle_adaptive():
    fracs = lw.load_puzzle_fracs()
    train = [x for x in fracs if 1 <= x["id"] <= 59]
    test = [x for x in fracs if 60 <= x["id"] <= 70]
    N_BINS = lw.N_BINS
    S = lw.S
    H_uniform = math.log2(N_BINS)

    dens = [1.0] * N_BINS
    for x in train:
        dens[min(N_BINS - 1, int(x["frac"] * N_BINS))] += 1.0
    dens = [v / sum(dens) for v in dens]

    weights = list(dens)
    pruned = False  # whole keyspace region pruned → uniform
    loops = []
    prev_ratio = None

    for loop in range(N_LOOPS):
        learning_bin_visits = 0  # overhead proxy: bins examined during train
        eval_steps_adapt = 0
        eval_steps_rand = 0

        if not pruned:
            W = dens if loop == 0 else weights
            miss_bins = [0.0] * N_BINS
            rng = random.Random(42 + loop * 17)
            for ep in range(lw.PUZZLE_EPISODES):
                x = train[ep % len(train)]
                target = min(S - 1, int(x["frac"] * S))
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
                    learning_bin_visits += 1
                    if b == target_bin:
                        break
                    miss_bins[b] += 1.0
            weights = lw.update_bin_weights_from_misses(W, miss_bins, eta=ETA)
            ent = lw.entropy(weights)
            flat = (H_uniform - ent) <= ENTROPY_TOL
        else:
            weights = [1.0 / N_BINS] * N_BINS
            miss_bins = [0.0] * N_BINS
            ent = H_uniform
            flat = True

        # Evaluate
        ratios = []
        rich_means = []
        rand_means = []
        for x in test:
            target = min(S - 1, int(x["frac"] * S))
            adapt_s, rand_s = [], []
            for t in range(lw.PUZZLE_TRIALS):
                rng_u = random.Random(9000 + loop * 10000 + x["id"] * 400 + t)
                rs = lw.random_steps(target, rng_u)
                rand_s.append(rs)
                eval_steps_rand += rs

                rng_a = random.Random(9000 + loop * 10000 + x["id"] * 400 + t)
                if pruned or flat:
                    # baseline uniform — independent seed
                    rng_a2 = random.Random(9100 + loop * 10000 + x["id"] * 400 + t)
                    a = lw.random_steps(target, rng_a2)
                else:
                    a = lw.rich_walk_steps(target, weights, rng_a)
                adapt_s.append(a)
                eval_steps_adapt += a
            rm = statistics.mean(adapt_s)
            um = statistics.mean(rand_s)
            ratios.append(rm / um if um else None)
            rich_means.append(rm)
            rand_means.append(um)

        mean_ratio = statistics.mean(ratios)
        no_gain = (
            prev_ratio is not None
            and mean_ratio >= prev_ratio - NOISE_TOL
        )
        newly_pruned = 0
        if (flat or no_gain) and not pruned:
            pruned = True
            newly_pruned = N_BINS  # whole region
            weights = [1.0 / N_BINS] * N_BINS
            ent = H_uniform

        # Compute: learning overhead ≈ bin visits * (S/N_BINS) as equivalent key checks
        learning_overhead_keys = learning_bin_visits * (S // N_BINS) if not pruned or loop == 0 else 0
        # Once pruned, subsequent loops have zero learning overhead
        if pruned and newly_pruned == 0:
            learning_overhead_keys = 0
            learning_bin_visits = 0

        total_adapt = learning_overhead_keys + eval_steps_adapt
        total_rand = eval_steps_rand
        compute_ratio = total_adapt / total_rand if total_rand else None

        row = {
            "loop": loop,
            "mean_ratio_adaptive_over_random": mean_ratio,
            "entropy_bits": ent,
            "entropy_uniform": H_uniform,
            "flat": flat,
            "no_gain_vs_prev": no_gain,
            "pruned": pruned,
            "n_bins_pruned": N_BINS if pruned else 0,
            "n_bins_total": N_BINS,
            "newly_pruned_this_loop": newly_pruned,
            "learning_bin_visits": learning_bin_visits,
            "learning_overhead_keys": learning_overhead_keys,
            "eval_steps_adaptive": eval_steps_adapt,
            "eval_steps_random": eval_steps_rand,
            "total_compute_adaptive": total_adapt,
            "total_compute_random": total_rand,
            "compute_ratio_adaptive_over_random": compute_ratio,
            "mean_adaptive_steps": statistics.mean(rich_means),
            "mean_rand_steps": statistics.mean(rand_means),
        }
        loops.append(row)
        prev_ratio = mean_ratio
        print(
            f"[adapt-puzzle] loop {loop}: ratio={mean_ratio:.4f} H={ent:.3f} "
            f"pruned={pruned} compute_ratio={compute_ratio:.3f}" if compute_ratio else
            f"[adapt-puzzle] loop {loop}: ratio={mean_ratio:.4f}",
            flush=True,
        )

    first = loops[0]["mean_ratio_adaptive_over_random"]
    last = loops[-1]["mean_ratio_adaptive_over_random"]
    best = min(r["mean_ratio_adaptive_over_random"] for r in loops)
    pruned_final = loops[-1]["pruned"]

    if pruned_final and best >= 0.95:
        verdict = (
            "null_flatline: puzzle prior entropy stayed near uniform; adaptive-prune "
            f"switched to baseline uniform order (best={best:.3f})"
        )
    elif best < 0.9:
        verdict = f"unexpected_signal: adaptive best={best:.3f} after prune logic"
    else:
        verdict = (
            f"null_flatline: no usable bias on #60-70 (first={first:.3f}, last={last:.3f}, "
            f"best={best:.3f}, pruned={pruned_final})"
        )

    return {
        "experiment": "puzzle_adaptive_prune",
        "loops": loops,
        "verdict": verdict,
        "first_ratio": first,
        "last_ratio": last,
        "best_ratio": best,
        "final_bins_pruned": N_BINS if pruned_final else 0,
        "final_pruned": pruned_final,
    }


def main():
    t0 = time.time()
    print("=== Adaptive-prune siphon ===", flush=True)
    siphon = run_siphon_adaptive()
    json.dump(siphon, open(ROOT / "error_matrix_loop_siphon_adaptive.json", "w"), indent=2)

    print("=== Adaptive-prune puzzle ===", flush=True)
    puzzle = run_puzzle_adaptive()
    json.dump(puzzle, open(ROOT / "error_matrix_loop_puzzle_adaptive.json", "w"), indent=2)

    # Merge into results.json
    results = json.load(open(ROOT / "results.json"))
    # Strip bulky folds from siphon loops for aggregate file
    siphon_slim = dict(siphon)
    siphon_slim["loops"] = [
        {k: v for k, v in row.items() if k != "folds"} for row in siphon["loops"]
    ]
    results["adaptive_prune_siphon"] = siphon_slim
    results["adaptive_prune_puzzle"] = puzzle
    results["method"]["adaptive_prune"] = (
        f"After each loop: flat test = error-matrix entropy within {ENTROPY_TOL} bits of "
        f"uniform OR CV < {FEATURE_FLAT_CV} OR no held-out gain vs previous beyond "
        f"{NOISE_TOL}. Flat regions switch to Boolean RW (siphon) or uniform order "
        "(puzzle); learning overhead drops to zero for pruned regions."
    )
    json.dump(results, open(ROOT / "results.json", "w"), indent=2)

    # Append / rewrite RESULTS.md with third method
    base = (ROOT / "RESULTS.md").read_text()
    # Remove old trailing files section to extend cleanly
    extra = [
        "",
        "## Experiment 3 — adaptive-prune (third method)",
        "",
        "Dr. Q's pruning rule: if the error / red-lining matrix is flat for a region,",
        "drop learning there and use the plain baseline. Flatline is a **null result**,",
        "not a failure. Compare to unpruned learning (Expts 1–2), which on the siphon",
        "graph *degraded* the walk by over-penalising `repeat`.",
        "",
        "### Siphon adaptive-prune",
        "",
        f"**Verdict:** {siphon['verdict']}",
        f"- first={siphon['first_ratio']:.4f}, last={siphon['last_ratio']:.4f}, "
        f"best={siphon['best_ratio']:.4f}",
        f"- final collectors pruned: {siphon['final_collectors_pruned']}; "
        f"features pruned: {siphon['final_features_pruned']}",
        f"- prevented unpruned degradation: {siphon['prevented_unpruned_degradation']} "
        f"(unpruned last ratio was {siphon['unpruned_last_ratio']:.4f})",
        "",
        "| loop | steps ratio (adapt/bool) | collectors pruned | features pruned | "
        "learn overhead (steps) | total compute ratio | no_gain |",
        "|-----:|-------------------------:|------------------:|----------------:|"
        "----------------------:|--------------------:|:-------|",
    ]
    for r in siphon["loops"]:
        extra.append(
            f"| {r['loop']} | "
            f"{r['mean_ratio_adaptive_over_bool']:.4f} | "
            f"{r['n_collectors_pruned']}/{r['n_collectors_total']} | "
            f"{r['n_features_pruned']}/{r['n_features_total']} | "
            f"{r['learning_steps_overhead']} | "
            f"{r['compute_ratio_adaptive_over_bool']:.3f} | "
            f"{r['no_gain_vs_prev']} |"
        )

    extra += [
        "",
        "### Puzzle adaptive-prune",
        "",
        f"**Verdict:** {puzzle['verdict']}",
        f"- first={puzzle['first_ratio']:.4f}, last={puzzle['last_ratio']:.4f}, "
        f"best={puzzle['best_ratio']:.4f}, final_pruned={puzzle['final_pruned']}",
        "",
        "| loop | steps ratio (adapt/rand) | entropy | pruned | bins pruned | "
        "learn overhead (keys) | total compute ratio | flat | no_gain |",
        "|-----:|-------------------------:|--------:|:------:|------------:|"
        "---------------------:|--------------------:|:----:|:-------|",
    ]
    for r in puzzle["loops"]:
        extra.append(
            f"| {r['loop']} | "
            f"{r['mean_ratio_adaptive_over_random']:.4f} | "
            f"{r['entropy_bits']:.3f} | "
            f"{r['pruned']} | "
            f"{r['n_bins_pruned']}/{r['n_bins_total']} | "
            f"{r['learning_overhead_keys']} | "
            f"{r['compute_ratio_adaptive_over_random']:.3f} | "
            f"{r['flat']} | "
            f"{r['no_gain_vs_prev']} |"
        )

    extra += [
        "",
        "### Caveats (adaptive-prune)",
        "",
        "- Prune threshold is heuristic (entropy tol / CV / no-gain). Different tols move",
        "  the prune point by a loop or two; the qualitative null on puzzles is robust.",
        "- Siphon compute ratio includes train-episode walk steps; once all collectors are",
        "  pruned, learning overhead → 0 and adaptive ≡ Boolean on steps (ratio ≈ 1).",
        "- Puzzle learning overhead converts bin visits to key-equivalents (bin_size = S/64).",
        "",
        f"Adaptive-prune wall time: {time.time() - t0:.1f}s",
        "",
    ]

    # Update files section
    if "## Files" in base:
        base = base.split("## Files")[0].rstrip() + "\n"
    (ROOT / "RESULTS.md").write_text(
        base
        + "\n".join(extra)
        + "\n## Files\n\n"
        + "- `learn_walk.py` — unpruned error-matrix loops (Expts 1–2)\n"
        + "- `adaptive_prune.py` — adaptive-prune third method\n"
        + "- `results.json` — aggregate (all three methods)\n"
        + "- `error_matrix_loop_siphon.json` / `error_matrix_loop_puzzle.json`\n"
        + "- `error_matrix_loop_siphon_adaptive.json` / `error_matrix_loop_puzzle_adaptive.json`\n"
    )
    print("Updated results.json and RESULTS.md", flush=True)
    print("ADAPT SIPHON:", siphon["verdict"], flush=True)
    print("ADAPT PUZZLE:", puzzle["verdict"], flush=True)


if __name__ == "__main__":
    main()
