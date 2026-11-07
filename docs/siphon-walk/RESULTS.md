# Siphon-walk: rich walk vs Boolean walk

Thesis tested: **rich walk > Boolean walk** on a graph that actually has structure
(real transfer/sweep edges around compromised wallets).

Read-only. Every edge in `graph.json` carries a `source` (Blockscout API URL,
Solana `getTransaction`, or Basescan page URL). No signing. No invented edges.

## Graph

- Nodes: **2441**
- Edges: **4959** (ethereum 3653, base 8, solana 1298)
- Seeds: `['0x78b5290269740033b05bd8d71c97331295eb5918', 'HtPtgMpK36z1u5duyRcXJ7rneNET9mivt4aSfLeTVw7m']`
- Collectors present: 7/7
- Reachable seed→collector pairs (BFS): **7** (all depth 1)

Base caveat: Base edges from live Basescan WebFetch this turn (native+ERC20 pages). Cloudflare blocked base.blockscout and eth_getLogs archive; only fully-resolved collector+delegation edges retained (no truncated-address invention).

## Methods

- **Boolean walk:** unweighted BFS (nodes expanded) + uniform random walk (steps to hit).
- **Rich walk:** edge weights from structural features with visit-memory penalty:
  same-second in/out pair count, outflow-share, repeat-recipient count,
  EIP-7702 delegation edge, near-zero residual after sweep. Default weights a priori.
- **Trials:** 200 random walks per pair, shared seeds so Boolean/Rich differ only by weights.
- **LOO:** leave-one-collector-out; pick W from a 4-point grid on other collectors; test on held-out.

## Results (random walk steps to collector)

| Collector | BFS depth | Bool mean steps | Rich mean steps | Ratio rich/bool | Bool hit rate | Rich hit rate |
|---|---:|---:|---:|---:|---:|---:|
| `0xeeeee90971b6…` | 1 | 82.69 | 39.37 | 0.476 | 0.38 | 0.28 |
| `0xf111122404b8…` | 1 | 56.47 | 46.60 | 0.825 | 0.09 | 0.03 |
| `0x8566263047ea…` | 1 | 61.32 | 31.66 | 0.516 | 0.38 | 0.32 |
| `0x09cbc0d92aab…` | 1 | 73.15 | 25.39 | 0.347 | 0.40 | 0.48 |
| `FncazAs6omJJjt…` | 1 | 19.65 | 4.82 | 0.245 | 1.00 | 1.00 |
| `5qmtDCvUreD8G5…` | 1 | 3.12 | 1.74 | 0.557 | 1.00 | 1.00 |
| `7jNPvxGzQ5wG5N…` | 1 | 150.75 | 187.04 | 1.241 | 1.00 | 1.00 |

**Aggregate mean ratio (default W): 0.601 → verdict `win`**

**LOO mean ratio: 0.605 → verdict `win`**

## Results (search expansion)

All collectors are **1 hop** from a seed. BFS therefore expands ~2 nodes and wins.
Rich best-first expands more (mean greedy/BFS expand ratio **19.29** → `loss`),
because high-weight non-collector edges get explored first.

| Collector | BFS expanded | Rich greedy expanded |
|---|---:|---:|
| `0xeeeee90971b6…` | 2 | 44 |
| `0xf111122404b8…` | 2 | 160 |
| `0x8566263047ea…` | 2 | 34 |
| `0x09cbc0d92aab…` | 2 | 4 |
| `FncazAs6omJJjt…` | 2 | 1 |
| `5qmtDCvUreD8G5…` | 2 | 2 |
| `7jNPvxGzQ5wG5N…` | 2 | 25 |

## Leakage caveats

Features (same_sec, out_share, repeat, delegation, near_zero) are computed from transfer structure only — they do not read collector labels. Feature *choice* and DEFAULT_W were specified by the task / prior siphon observations (leakage of design). LOO tunes W on other collectors and tests on held-out collector.

- Features do **not** include a collector-label bit.
- Feature *menu* and DEFAULT_W come from the same siphon observations that named the collectors
  (design leakage). LOO still shows ~0.60 ratio, so the win is not an artifact of tuning W on the test label.
- One Solana collector (`7jNPvx…`) is a **loss** for rich RW (ratio 1.24): it is a late dust drain,
  not a same-second / high out-share pattern — honest counterexample inside the win.
- Cross-chain edges do not exist in this graph (ETH/Base and Solana are separate components).

## Verdict

On this real siphon graph:

1. **Random walk with memory: rich walk WINS** (~0.60× steps of Boolean; holds under LOO).
2. **Shortest-path search when target is depth-1: Boolean BFS WINS** (rich greedy expands more).

So the thesis **rich walk > Boolean walk** holds for *walks* (sequential exploration under uncertainty),
not for *informed search against a known 1-hop target*. That matches the Bitcoin-puzzle framing:
kangaroo is already a walk; richness helps when you do not know which neighbor is the sink.

## Files

- `graph.json` — edges with per-edge `source`
- `walk.py` — experiment
- `results.json` — raw numbers

SHA-256 of this RESULTS.md is computed after write; see commit message / digest file.
