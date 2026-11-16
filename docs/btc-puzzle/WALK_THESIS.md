# Walk thesis: can measured structure beat √-space Boolean search?

**Date:** 22 Oct 2026 (America/New_York)  
**Stance:** digests and measurements only. No P=NP claim. No mainnet spend. No honeypot keys.

## 1. What kangaroo already is

Pollard's kangaroo (and BSGS) is a **random walk on the ECDLP graph**:
- Nodes are elliptic-curve points; edges are additions of jump sizes.
- Distinguished points give collisions; the hidden scalar is recovered from tame/wild distances.
- Expected group operations scale as **Θ(√W)** for a window of width W, when a **public key** is known.
- That walk is “Boolean” in Dr. Q’s sense: each step is an unstructured group add; the only geometry is the cyclic group itself. There are no edge weights from the outside world.

Our demo on solved #30/#40/#50 (`experiments/kangaroo_results.json`) measured brute/kang op ratios from ~3.6× (W=4k) to ~27× (W=262k). That is the √-space baseline when a pubkey exists. Unsolved #71+ generally **lack** exposed pubkeys, so kangaroo does not apply to them as-is.

## 2. What a NON-Boolean / richer walk would have to mean

A richer walk needs **edge weights or transition bias from observed structure**, not only group law. Candidates we actually have on hand:

| Candidate structure | What we measured | Transfers to keyspace? |
|---|---|---|
| Solved-key position in range | frac mean≈0.51, sd≈0.27 (uniform-like); χ² 16-bin train=14.6 < 25 | **No** — flat prior |
| Active-bit nibbles | χ²≈19.4 on 992 nibbles — uniform-consistent | **No** |
| Vanity prefixes (eeee / f111 / 8566 / 0078) | **0 hits** in solved pk/addr/hash160 | **No** in puzzle set |
| Concurrent multi-chain siphon timing | HtPtgM dust @ t+2s; ETH `0xeeee`/`0xf111`/`0x8566` vs `0x78` narrative | **Pending** as workspace data; not folded into weights yet |
| EIP-7702 delegation graphs | Mentioned in narrative | **Pending** — no local dataset |
| Dep-graph bifurcation (geth / jito / mempool / PHP) | Real degree skew (jito max deg 79, median 9) | **Alien prior** — structure of *code*, not of *keys* |
| PmllAnchor digests | Sepolia + Stellar roots for coverage | Bookkeeping only; no key bias |

A richer walk that **wins** would visit high-weight regions first and hit held-out keys in fewer probes than Uniform(1..S), and do so **without** relying on the ECDLP √ collision trick.

## 3. Claims vs hypotheses vs falsifiers

### (a) Supported by our measured data
1. Solved Bitcoin puzzle keys are consistent with **uniform** draws inside their bit ranges (position + active nibbles).
2. **Center-out / quartile walks do not beat random** on held-out #60–70 (mean ratios 1.15 / 1.16). See `experiments/hidden_key_results.json`.
3. **Kangaroo beats linear brute** on tiny windows around *known* keys with pubkeys (√-ish measured speedup).
4. privatekeys.pw is a **directory + CSV**, not a pattern/heatmap oracle (`PATTERN_NOTES.md`).
5. Honeypot HtPtgM showed **dust/poison + self-signed outs**, not a confirmed external sweeper (`/workspace/honeypot-mock/`).
6. Coverage of puzzles + #71 subrange is **anchored** (digests only) on Sepolia + Stellar (`pmll_nodes/`).

### (b) Hypotheses (open)
1. Concurrent ETH siphon bots (`0xeeee…`, `0xf111…008`, `0x8566…`) and Solana HtPtgM timing share a **scheduler fingerprint** that could weight a multi-chain event graph — useful for *detection*, not for deriving secp256k1 scalars.
2. EIP-7702 delegation edges might yield a **contract-control graph** with hubs — again a malware/ops graph, not a keyspace prior unless someone reuses vanity nonces as keys (unproven).
3. Dep-graph “bifurcation” language may describe **PMLL memory traversal** for code intelligence; equating that to ECDLP shortcuts is a category error unless a reduction is exhibited.

### (c) Falsifiers
1. **Keyspace prior falsifier (run):** train density on #3–59, test walk on #60–70. If mean steps / random ≥ 0.9, the “rich pathway through nodes” claim for *keys* fails.
2. **Alien prior falsifier (run):** weight bins by jito-solana degree histogram. Same threshold.
3. **Sqrt-Boolean falsifier (run):** reorder √-sized blocks only. If it ties random, “Boolean √ walk without pubkey” is not a shortcut — it only *organizes* the same linear scans.
4. **Would support a real shortcut:** a walk, frozen before seeing #60–70 keys, with mean ratio ≤ 0.5 across those eleven puzzles, replicated on another held-out band (#50–59), with code + seed published.

## 4. Experiment: `experiments/rich_walk.py`

**Setup:** S=2²⁰ scaled ranges; 64-bin weighted graph; 400 trials/puzzle; held-out #60–70.

**Correlation gate (before weighting):** no vanity correlation; position/nibbles uniform-consistent → `rich_walk_correlation.json`.

**Results (mean steps / random):**

| Method | Mean ratio vs random | Notes |
|---|---:|---|
| rich_density (#3–59 frac prior) | **0.994** | Entropy 5.85 vs uniform 6.0 — nearly flat |
| rich_alien (jito degree prior) | **1.089** | Alien structure does not transfer |
| sqrt_block (Boolean √ blocks) | **1.018** | Ties random (same key checks) |
| kangaroo ECDLP ref (if pubkey) | **2048 steps** (= 2√S) | Reference only — not available without pubkey |

**Verdict: FALSIFIED** — no faster non-√ walk appeared on this held-out set.  
`faster_non_sqrt_walk_appeared: false` in `experiments/rich_walk_results.json`.

Per-puzzle noise exists (e.g. #69 alien ratio 0.47 by luck of bin weights); **means** across #60–70 are what the falsifier uses.

## 5. Siphon / EIP-7702 status

Searched `/workspace` for siphon / `0xeeee` / `0xf111` / `0x8566` / EIP-7702 result artifacts tied to this work: **none landed**. Narrative remains pending; honeypot mock covers Solana dust/self-out patterns only. When ETH traces arrive, fold them as a *detection* graph experiment — do not silently treat them as secp256k1 key priors.

## 6. How this sits next to PMLL

PMLL dep graphs (PHP/JS/Rust/Go) and PmllAnchor digests are the right tool for **recording which subranges and which code units were examined**. They do not, on present evidence, induce a walk that beats Uniform on puzzle keyspaces. The honest “fast pathway” that *does* exist remains: **kangaroo/BSGS when a pubkey is exposed**, which is still Θ(√W) group algebra — Boolean √-space — not a richer weighted shortcut from multi-chain folklore.

## 7. Bottom line for Dr. Q

We looked for a richer-than-kangaroo walk grounded in the data points so far.  
**Measured structure in the puzzle CSV does not bias keyspace.**  
**Imported dep-graph weights do not help.**  
**Sqrt-block Boolean reorganization does not help.**  
A faster non-√ walk is **falsified** on #60–70 scaled instances.  
Kangaroo remains the only demonstrated sublinear probe class — and only with pubkeys.
