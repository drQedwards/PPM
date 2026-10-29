# Promise harness — ancestral prune with error feedback

Promise library: **q@1.5.1** (npm `q`).

Each generation keeps `parentPtr` and `lastImprovedPtr`.
`tryChild(parent)` is a Q promise: resolves only if the child beats the parent
on the same data (mean steps, 1% margin); else rejects with
`{loser, data, deltaSteps, errorMatrix}` and that error feeds the next child.

Two stop modes on the same data/seeds:
- **flat_for_N** — wait N consecutive rejections, then fall back to `lastImprovedPtr`.
- **early_break** — on first flat error signal, the flatline is itself the pointer: jump to `lastImprovedPtr` immediately.

## Siphon graph

- Graph: 2441 nodes, 4959 edges, 7 reachable pairs.
- trials/LOO=80, train episodes/collector=30, maxGens=8, flatN=2.
- Prior static rich RW: 0.60× Boolean; prior adaptive-prune best: 0.50×.

### flat_for_N

- stop=flat_for_N, prunedAt=2, nGens=3
- best gen=0 meanSteps=53.4 ± 160.8 vsBool=0.6261
- totalWalkSteps=9340662, totalWallMs=51724

| gen | status | parent | lastImproved | mean steps | stdev | vs parent | vs bool | flat |
|----:|:-------|-------:|-------------:|-----------:|------:|----------:|--------:|:----:|
| 0 | resolved | — | 0 | 53.4 | 160.8 | — | 0.6261 | N |
| 1 | rejected | 0 | 0 | 53.4 | 160.8 | 1.0000 | 0.6261 | N |
| 2 | rejected | 1 | 0 | 97.0 | 312.6 | 1.8184 | 0.9509 | N |

### early_break

- stop=max_gens, jumpedAt=null, nGens=8
- best gen=0 meanSteps=53.4 ± 160.8 vsBool=0.6261
- finalAncestor gen=0 (best fulfilled ancestor)
- totalWalkSteps=23437164, totalWallMs=125318

| gen | status | parent | lastImproved | mean steps | stdev | vs parent | vs bool | flat |
|----:|:-------|-------:|-------------:|-----------:|------:|----------:|--------:|:----:|
| 0 | resolved | — | 0 | 53.4 | 160.8 | — | 0.6261 | N |
| 1 | rejected | 0 | 0 | 53.4 | 160.8 | 1.0000 | 0.6261 | N |
| 2 | rejected | 1 | 0 | 97.0 | 312.6 | 1.8184 | 0.9509 | N |
| 3 | rejected | 2 | 0 | 141.9 | 443.0 | 1.4625 | 1.2893 | N |
| 4 | rejected | 3 | 0 | 142.5 | 438.0 | 1.0041 | 1.2986 | N |
| 5 | resolved | 4 | 0 | 139.2 | 437.9 | 0.9767 | 1.2738 | N |
| 6 | rejected | 5 | 0 | 138.7 | 436.7 | 0.9968 | 1.2829 | N |
| 7 | resolved | 6 | 0 | 132.3 | 439.1 | 0.9537 | 1.2296 | N |

### Savings (early_break vs flat_for_N)

| metric | flat_for_N | early_break | saved |
|-------:|-----------:|------------:|------:|
| generations run | 3 | 8 | -5 |
| walk steps | 9340662 | 23437164 | -14096502 |
| wall ms (sum gen) | 51724 | 125318 | -73594 |
| wall ms (all) | 51726 | 125336 | -73610 |


Note: on this siphon run the miss-feature error matrix never flatlined (flat=N every gen), so early_break had nothing to jump on and ran to maxGens; flat_for_N stopped after 2 consecutive rejections. Early break therefore **cost** 5 generations / 14,096,502 walk steps / ~74s here — not a win on this graph.

**vs prior 0.50×:** this harness best vsBool = 0.6261 — does **not** beat prior adaptive-prune best 0.50×.

## Puzzle keys (#1–#59 train → #60–#70 eval, S=2^20, 64 bins)

- trials/puzzle=200, train episodes=60.

### flat_for_N

- stop=flat_for_N, prunedAt=2, nGens=3
- best gen=0 meanSteps=508944 vsRand=0.9687
- totalWalkSteps=11973, keyEquiv=85082112, totalWallMs=43

| gen | status | parent | lastImproved | mean steps | stdev | vs parent | vs rand | flat |
|----:|:-------|-------:|-------------:|-----------:|------:|----------:|--------:|:----:|
| 0 | resolved | — | 0 | 508944 | 300536 | — | 0.9687 | Y |
| 1 | rejected | 0 | 0 | 508944 | 300536 | 1.0000 | 0.9687 | Y |
| 2 | rejected | 1 | 0 | 508155 | 300452 | 0.9984 | 0.9671 | Y |

### early_break

- stop=early_break_flatline, jumpedAt=1, nGens=2
- best gen=0 meanSteps=508944 vsRand=0.9687
- totalWalkSteps=7992, keyEquiv=56885248, totalWallMs=18

| gen | status | parent | lastImproved | mean steps | stdev | vs parent | vs rand | flat |
|----:|:-------|-------:|-------------:|-----------:|------:|----------:|--------:|:----:|
| 0 | resolved | — | 0 | 508944 | 300536 | — | 0.9687 | Y |
| 1 | rejected | 0 | 0 | 508944 | 300536 | 1.0000 | 0.9687 | Y |

### Savings (early_break vs flat_for_N)

| metric | flat_for_N | early_break | saved |
|-------:|-----------:|------------:|------:|
| generations run | 3 | 2 | 1 |
| walk steps | 11973 | 7992 | 3981 |
| key-equiv | 85082112 | 56885248 | 28196864 |
| wall ms (sum gen) | 43 | 18 | 25 |
| wall ms (all) | 45 | 18 | 27 |

**Puzzle:** ratios near 1.0 — flat prior; early_break is expected to fire immediately after gen 0's child if the miss-bin signal is flat.

## Method notes

- Beat rule: child mean steps < parent mean steps × 0.99 (same seeds/pairs).
- Rejection error feeds next child via multiplicative weights (η=0.25), same as learn_walk.py.
- Flat error = near-uniform miss-feature entropy or low CV (siphon); near-uniform miss bins (puzzle).
- keyhunt / Cowcraft untouched; this process runs at nice 19.

## Files

- `run.js` — entry
- `lib/harness.js` — siphon Q lineage + pointers
- `lib/puzzle_harness.js` — puzzle Q lineage + pointers
- `out/results.json` — full measured dump

