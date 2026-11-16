# Learning walk — error / red-lining matrix loops

Rich walk that remembers past failed diagonals: miss nodes (or bins) form an
error matrix; multiplicative-weights updates push the next loop off those misses.
Leave-one-collector-out (siphon) and held-out puzzles #60–#70 keep the walk from
memorising answers. Numbers are from live runs on real graph / export.csv data.

## Experiment 1 — siphon graph

- Graph: 2441 nodes, 4959 edges, 7 reachable seed→collector pairs.
- Loops: 8; trials/LOO fold: 120; train episodes/collector/loop: 40; η=0.25.
- Prior static rich RW (no learning): 0.60× Boolean RW (LOO 0.605×); counterexample `7jNPvx…` 1.24×.

| loop | mean ratio (rich/bool LOO) | mean bool steps | mean rich steps | 7jNPvx ratio | W (rounded) |
|-----:|---------------------------:|----------------:|----------------:|-------------:|:------------|
| 0 | 0.7249 | 71.2 | 71.3 | 2.348 | `same_sec=3.00, out_share=1.95, repeat=0.30, delegation=5.00, near_zero=1.95` |
| 1 | 1.2804 | 64.1 | 152.6 | 6.419 | `same_sec=3.00, out_share=1.90, repeat=0.09, delegation=5.00, near_zero=1.91` |
| 2 | 1.6873 | 60.0 | 200.0 | 8.653 | `same_sec=2.99, out_share=1.86, repeat=0.05, delegation=5.00, near_zero=1.86` |
| 3 | 1.5972 | 79.1 | 194.1 | 8.734 | `same_sec=2.97, out_share=1.81, repeat=0.05, delegation=5.00, near_zero=1.82` |
| 4 | 1.9286 | 74.5 | 236.1 | 10.489 | `same_sec=2.96, out_share=1.77, repeat=0.05, delegation=5.00, near_zero=1.77` |
| 5 | 1.8644 | 64.6 | 225.5 | 10.499 | `same_sec=2.95, out_share=1.72, repeat=0.05, delegation=5.00, near_zero=1.73` |
| 6 | 1.8403 | 54.0 | 191.5 | 8.794 | `same_sec=2.93, out_share=1.68, repeat=0.05, delegation=5.00, near_zero=1.69` |
| 7 | 1.4954 | 72.5 | 191.4 | 7.202 | `same_sec=2.92, out_share=1.64, repeat=0.05, delegation=5.00, near_zero=1.65` |

**Verdict:** loop-0 rich walk still beats Boolean (0.72×), but **unpruned learning degraded** the walk (→1.50× by loop 7) by crushing `repeat`. Learning did not improve; it hurt. Flatline-after-degrade is why adaptive-prune exists.
- first=0.7249, last=1.4954, best=0.7249, learning_improved=False, 7jNPvx_improved=False

### Caveats (siphon)

- Feature *choice* still comes from prior siphon observations (design leakage); LOO only
  protects weight learning, not feature invention.
- Miss definition uses BFS shortest path as the 'true' diagonal; other shortest paths
  or multi-hop collectors may mis-label some nodes as misses.
- When BFS depth is 1, Boolean BFS already wins on expand count; this experiment scores
  random walks, not expanders.

## Experiment 2 — Bitcoin puzzle positions (#1–#59 train → #60–#70 eval)

- S=2^20, bins=64, trials/puzzle=400, loops=8.
- Train n=58; test ids=[60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70].

| loop | mean ratio (rich/random) | entropy (bits) | uniform entropy | mean rich steps | mean rand steps |
|-----:|-------------------------:|---------------:|----------------:|----------------:|----------------:|
| 0 | 0.9509 | 5.851 | 6.000 | 501438 | 527248 |
| 1 | 0.9598 | 5.853 | 6.000 | 507405 | 530160 |
| 2 | 0.9398 | 5.855 | 6.000 | 501730 | 534731 |
| 3 | 0.9706 | 5.857 | 6.000 | 508427 | 523828 |
| 4 | 0.9446 | 5.858 | 6.000 | 496021 | 524734 |
| 5 | 0.9939 | 5.860 | 6.000 | 510498 | 515168 |
| 6 | 0.9626 | 5.862 | 6.000 | 508212 | 528769 |
| 7 | 0.9724 | 5.864 | 6.000 | 506716 | 521901 |

**Verdict:** ratios 0.94–0.99 with entropy 5.85/6.00 bits — within noise of uniform. Treated as a **null / flat** prior (adaptive-prune confirms and switches to baseline).
- first=0.9509, last=0.9724, best=0.9398, learning_improved=False

### Caveats (puzzle)

- Only fractional *position* within each puzzle range is used (no pubkey, no kangaroo).
- Uniform keyspace: AM–GM / Shoup already say no sub-√N generic walk; this tests whether
  an error-matrix prior can still bias #60–#70. Expect ≈1.0×.
- Density prior at loop 0 matches the earlier falsified rich_walk; subsequent loops
  only reweight bins from train misses.

## Method

Miss nodes = visited nodes not on BFS shortest path to collector (siphon), or exhausted bins before target bin (puzzle). Feature aggregates over misses update weights via multiplicative weights W *= exp(-eta * miss_frac).

Siphon: leave-one-collector-out each loop. Puzzle: train #1-59, eval #60-70 on S=2^20.

## Experiment 3 — adaptive-prune (third method)

Dr. Q's pruning rule: if the error / red-lining matrix is flat for a region,
drop learning there and use the plain baseline. Flatline is a **null result**,
not a failure. Compare to unpruned learning (Expts 1–2), which on the siphon
graph *degraded* the walk by over-penalising `repeat`.

### Siphon adaptive-prune

**Verdict:** win: adaptive-prune kept rich walk where signal exists and cut flat regions; avoided unpruned degradation (unpruned_last=1.495, adapt_last=0.819)
- first=0.8076, last=0.8192, best=0.5020
- final collectors pruned: 7; features pruned: 5
- prevented unpruned degradation: True (unpruned last ratio was 1.4954)

| loop | steps ratio (adapt/bool) | collectors pruned | features pruned | learn overhead (steps) | total compute ratio | no_gain |
|-----:|-------------------------:|------------------:|----------------:|----------------------:|--------------------:|:-------|
| 0 | 0.8076 | 1/7 | 4/5 | 2088124 | 2.082 | False |
| 1 | 0.5020 | 1/7 | 4/5 | 1764116 | 1.877 | False |
| 2 | 0.5655 | 7/7 | 5/5 | 1688221 | 1.889 | True |
| 3 | 1.1015 | 7/7 | 5/5 | 0 | 1.018 | True |
| 4 | 1.2121 | 7/7 | 5/5 | 0 | 1.019 | True |
| 5 | 1.0407 | 7/7 | 5/5 | 0 | 0.942 | False |
| 6 | 0.9870 | 7/7 | 5/5 | 0 | 1.022 | False |
| 7 | 0.8192 | 7/7 | 5/5 | 0 | 1.080 | False |

### Puzzle adaptive-prune

**Verdict:** null_flatline: puzzle prior entropy stayed near uniform; adaptive-prune switched to baseline uniform order (best=0.998)
- first=1.0003, last=0.9990, best=0.9978, final_pruned=True

| loop | steps ratio (adapt/rand) | entropy | pruned | bins pruned | learn overhead (keys) | total compute ratio | flat | no_gain |
|-----:|-------------------------:|--------:|:------:|------------:|---------------------:|--------------------:|:----:|:-------|
| 0 | 1.0003 | 6.000 | True | 64/64 | 30588928 | 1.013 | True | False |
| 1 | 1.0027 | 6.000 | True | 64/64 | 0 | 1.003 | True | True |
| 2 | 1.0000 | 6.000 | True | 64/64 | 0 | 1.000 | True | True |
| 3 | 0.9983 | 6.000 | True | 64/64 | 0 | 0.998 | True | True |
| 4 | 0.9978 | 6.000 | True | 64/64 | 0 | 0.998 | True | True |
| 5 | 1.0010 | 6.000 | True | 64/64 | 0 | 1.000 | True | True |
| 6 | 1.0011 | 6.000 | True | 64/64 | 0 | 1.001 | True | True |
| 7 | 0.9990 | 6.000 | True | 64/64 | 0 | 0.999 | True | True |

### Caveats (adaptive-prune)

- After all collectors are pruned, adapt≡Boolean; residual ratio≠1 is RNG noise between two independent Boolean walks, not a real gain.
- Prune threshold is heuristic (entropy tol / CV / no-gain). Different tols move
  the prune point by a loop or two; the qualitative null on puzzles is robust.
- Siphon compute ratio includes train-episode walk steps; once all collectors are
  pruned, learning overhead → 0 and adaptive ≡ Boolean on steps (ratio ≈ 1).
- Puzzle learning overhead converts bin visits to key-equivalents (bin_size = S/64).

Adaptive-prune wall time: 125.4s

## Files

- `learn_walk.py` — unpruned error-matrix loops (Expts 1–2)
- `adaptive_prune.py` — adaptive-prune third method
- `results.json` — aggregate (all three methods)
- `error_matrix_loop_siphon.json` / `error_matrix_loop_puzzle.json`
- `error_matrix_loop_siphon_adaptive.json` / `error_matrix_loop_puzzle_adaptive.json`
