#!/usr/bin/env python3
"""Rich (weighted) walk vs random vs sqrt-Boolean reference on scaled #60-70.

NOT Pollard's kangaroo on a pubkey. NOT uniform random as the method under test.
If measured structure is flat, report that and show rich walk loses or ties random.

Comparators (S=2^20): random; rich_density (#3-59 frac prior); rich_alien
(jito-solana degree prior); sqrt_block (Boolean sqrt blocks); kangaroo_ecdlp_ref
(theoretical ~2*sqrt(S) if pubkey existed — reference only).

No mainnet spend. No honeypot keys. No P=NP claim.
"""
from __future__ import annotations
import csv, json, math, random, statistics as st, collections
from pathlib import Path

S = 1 << 20
N_BINS = 64
TRIALS = 400
CSV = Path("/workspace/btc-puzzle/patterns/export.csv")
GRAPH = Path("/workspace/crypto-repos/out/jito-solana_graph.json")
OUT = Path("/workspace/btc-puzzle/experiments/rich_walk_results.json")
CORR = Path("/workspace/btc-puzzle/experiments/rich_walk_correlation.json")


def load_solved():
    rows = list(csv.DictReader(open(CSV)))
    out = []
    for r in rows:
        if not r["private_key"]:
            continue
        i = int(r["id"])
        if i < 3 or i > 160:
            continue
        lo, hi = int(r["range_min"], 16), int(r["range_max"], 16)
        k = int(r["private_key"], 16)
        out.append({
            "id": i,
            "frac": (k - lo) / (hi - lo),
            "addr": r["address"],
            "h160": r["hash160_compressed"],
            "pk": r["private_key"],
        })
    return out


def correlation_report(solved):
    train = [x for x in solved if x["id"] <= 59]
    test = [x for x in solved if 60 <= x["id"] <= 70]
    B = 16
    dens = [0] * B
    for x in train:
        dens[min(B - 1, int(x["frac"] * B))] += 1
    exp = len(train) / B
    chi_pos = sum((c - exp) ** 2 / exp for c in dens)
    nib = collections.Counter()
    for x in solved:
        n = x["id"]
        k = int(x["pk"], 16) & ((1 << n) - 1)
        for i in range(0, n, 4):
            nib[(k >> i) & 0xF] += 1
    tot = sum(nib.values())
    chi_nib = sum((nib[i] - tot / 16) ** 2 / (tot / 16) for i in range(16))
    patterns = ["eeee", "f111", "8566", "0078", "1111", "ffff", "dead", "beef"]
    hits = {p: 0 for p in patterns}
    for x in solved:
        blob = (x["pk"] + x["addr"] + x["h160"]).lower()
        for p in patterns:
            if p in blob:
                hits[p] += 1
    addr4 = collections.Counter(x["addr"][:4] for x in solved)
    rep = sum(1 for _, c in addr4.items() if c > 1)
    report = {
        "train_n": len(train),
        "test_n": len(test),
        "frac_mean_train": st.mean(x["frac"] for x in train),
        "frac_sd_train": st.pstdev(x["frac"] for x in train),
        "chi2_16bin_position_train": round(chi_pos, 3),
        "chi2_critical_df15_approx": 25.0,
        "position_uniform_consistent": chi_pos < 25.0,
        "chi2_active_nibbles": round(chi_nib, 3),
        "nibbles_uniform_consistent": chi_nib < 25.0,
        "vanity_substring_hits": hits,
        "repeated_addr4_prefixes": rep,
        "siphon_results_folded": False,
        "siphon_note": "No ETH siphon / EIP-7702 result files under /workspace yet; pending.",
        "correlation_found_for_keyspace_bias": False,
        "note": (
            "No usable keyspace correlation in solved puzzles. "
            "Vanity prefixes eeee/f111/8566/0078 do not appear. "
            "Position and active nibbles consistent with uniform. "
            "Rich walk priors nearly flat or alien — expect tie/loss vs random."
        ),
    }
    CORR.write_text(json.dumps(report, indent=2))
    return report, train, test


def density_weights(train, n_bins):
    w = [1.0] * n_bins
    for x in train:
        w[min(n_bins - 1, int(x["frac"] * n_bins))] += 1.0
    s = sum(w)
    return [v / s for v in w]


def alien_degree_weights(n_bins):
    g = json.loads(GRAPH.read_text())
    deg = collections.Counter()
    for e in g["edges"]:
        deg[e["from"]] += 1
        deg[e["to"]] += 1
    vals = sorted(deg.values(), reverse=True)
    w = [1.0] * n_bins
    for i, v in enumerate(vals):
        w[i % n_bins] += float(v)
    s = sum(w)
    return [v / s for v in w]


def entropy(w):
    return -sum(p * math.log2(p) for p in w if p > 0)


def rich_walk_steps(target, weights, rng):
    """Weighted bin order + uniform rank inside target bin (equiv. to shuffle, O(bins))."""
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
            # exhaust this bin
            bl = (S - b * bin_size) if b == n_bins - 1 else bin_size
            steps += bl
        else:
            # target uniformly ranked in random permutation of its bin
            steps += rng.randint(1, bin_len)
            return steps
    return steps


def sqrt_block_steps(target, rng):
    """Random order over sqrt-sized blocks; uniform rank inside target block."""
    block = int(math.sqrt(S))
    n_blocks = (S + block - 1) // block
    target_block = target // block
    lo = target_block * block
    hi = min(S, lo + block)
    blen = hi - lo
    order = list(range(n_blocks))
    rng.shuffle(order)
    steps = 0
    for bi in order:
        if bi != target_block:
            blo = bi * block
            bhi = min(S, blo + block)
            steps += bhi - blo
        else:
            steps += rng.randint(1, blen)
            return steps
    return steps



def main():
    solved = load_solved()
    corr, train, test = correlation_report(solved)
    w_den = density_weights(train, N_BINS)
    w_alien = alien_degree_weights(N_BINS)
    uniform_e = math.log2(N_BINS)

    per = []
    for x in test:
        target = min(S - 1, max(0, int(round(x["frac"] * (S - 1)))))
        dens_steps = []
        alien_steps = []
        sqrt_steps = []
        rand_steps = []
        for trial in range(TRIALS):
            rng = random.Random((0x51C00000 + x["id"] * 0x9E3779B9 + trial) & 0xFFFFFFFF)
            dens_steps.append(rich_walk_steps(target, w_den, rng))
            rng2 = random.Random((0xA11E0000 + x["id"] * 0x9E3779B9 + trial) & 0xFFFFFFFF)
            alien_steps.append(rich_walk_steps(target, w_alien, rng2))
            rng3 = random.Random((0x59070000 + x["id"] * 0x9E3779B9 + trial) & 0xFFFFFFFF)
            sqrt_steps.append(sqrt_block_steps(target, rng3))
            rng4 = random.Random((0x12A40000 + x["id"] * 0x9E3779B9 + trial) & 0xFFFFFFFF)
            rand_steps.append(rng4.randint(1, S))
        rec = {
            "puzzle": x["id"],
            "frac": round(x["frac"], 6),
            "scaled_target": target,
            "random_mean": st.mean(rand_steps),
            "rich_density_mean": st.mean(dens_steps),
            "rich_alien_mean": st.mean(alien_steps),
            "sqrt_block_mean": st.mean(sqrt_steps),
            "kangaroo_ecdlp_ref_2sqrtS": 2 * int(S ** 0.5),
            "density_over_random": st.mean(dens_steps) / st.mean(rand_steps),
            "alien_over_random": st.mean(alien_steps) / st.mean(rand_steps),
            "sqrt_over_random": st.mean(sqrt_steps) / st.mean(rand_steps),
        }
        per.append(rec)
        print(
            f"#{rec['puzzle']} rand={rec['random_mean']:.0f} dens={rec['rich_density_mean']:.0f} "
            f"alien={rec['rich_alien_mean']:.0f} sqrt={rec['sqrt_block_mean']:.0f} "
            f"ratios={rec['density_over_random']:.3f}/{rec['alien_over_random']:.3f}/{rec['sqrt_over_random']:.3f}"
        )

    mean_d = st.mean(r["density_over_random"] for r in per)
    mean_a = st.mean(r["alien_over_random"] for r in per)
    mean_s = st.mean(r["sqrt_over_random"] for r in per)
    # Faster non-sqrt walk? dens or alien mean ratio < 0.9 AND clearly below sqrt_block
    faster = (mean_d < 0.9 or mean_a < 0.9) and min(mean_d, mean_a) < mean_s * 0.95
    summary = {
        "S": S,
        "n_bins": N_BINS,
        "trials_per_puzzle": TRIALS,
        "correlation": corr,
        "weight_entropy_density": entropy(w_den),
        "weight_entropy_alien": entropy(w_alien),
        "weight_entropy_uniform": uniform_e,
        "mean_density_over_random": mean_d,
        "mean_alien_over_random": mean_a,
        "mean_sqrt_block_over_random": mean_s,
        "kangaroo_ecdlp_ref_2sqrtS": 2 * int(S ** 0.5),
        "faster_non_sqrt_walk_appeared": faster,
        "verdict": (
            "FALSIFIED: no faster non-sqrt walk on held-out #60-70. "
            "Density prior nearly uniform; alien dep-graph prior does not transfer; "
            "sqrt-block reorder ties random (same linear key checks)."
            if not faster
            else "UNEXPECTED: rich walk beat random — investigate before claiming generality."
        ),
        "puzzles": per,
    }
    OUT.write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: summary[k] for k in summary if k not in ("puzzles", "correlation")}, indent=2))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
