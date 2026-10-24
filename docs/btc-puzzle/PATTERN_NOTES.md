# Bitcoin puzzle pattern notes (22 Oct 2026, EDT)

## Sources (read-only)
- https://privatekeys.pw/bitcoin-puzzle -> patterns/puzzle.html
- https://privatekeys.pw/bitcoin-puzzle/export?status=all -> patterns/export.csv (256 rows: 83 solved, 96 moved, 77 unsolved)
- The site shows only a directory: ID, status, bit range, hex range, address, value, hash160, pubkey, known privkey. It has no heatmaps, pattern images, or geometric claims. The only images are its logo and favicons.

## Analysis (analyze.py -> patterns/solved_key_positions.png)
For the 81 solved keys from #3 to #160, I measured where each key sits in its range as (k-lo)/(hi-lo):
- mean 0.514, median 0.502, sd 0.270 (a uniform spread gives 0.5 / 0.5 / 0.289)
- by quartile: 16 / 24 / 23 / 17. There is no visible clustering.
- The share of 1-bits in each key averages 0.504, which is what random keys give.
- Conclusion: there is no exploitable positional pattern. This is consistent with keys taken from one random source and masked to n bits.
- Unsolved puzzles with an exposed pubkey: #140, #145, #150, #155, #160. Those allow O(sqrt N) kangaroo/BSGS search, about 2^70+ steps, which is still out of reach. #71 to #79 and the others have no pubkey, so they can only be searched by hash160 brute force.

## "Fast pathway through nodes"
- Kangaroo and BSGS already are graph-walk shortcuts: pseudo-random walks on the EC group that collide in about sqrt(N). They are generic, proven optimal for generic-group algorithms, and need a pubkey.
- A PMLL keyspace graph would only beat a linear scan if its edges carry information that correlates with the hidden key. The EC map and hash160 are designed to remove exactly that correlation.
- None of this bears on P vs NP. ECDLP is not known to be NP-hard, and a P=NP proof would not by itself make a fast algorithm available.
- What would falsify the claim: any traversal or priming method that finds the keys of solved puzzles (held out, #60 to #70) in fewer expected steps than random search over many trials. If it doesn't beat the uniform baseline, the claim fails.

## Cross-links
The go-ethereum, jito, mempool, and PHP graphs and the PmllAnchor roots are dependency graphs of code. They contain no information about keys. PMLL is useful here only as bookkeeping: store the searched subranges as nodes, hash them, and anchor the progress roots.

## Next experiments (low CPU, nice 19)
1. Held-out test: hide the solved keys for #60 to #70, run any proposed "pathway" heuristic against a seeded random baseline, and compare step counts.
2. Load export.csv into PMLL as nodes (puzzle, range, hash160, status), with edges to the subranges that keyhunt has covered. Anchor a digest of the coverage.
3. Run a small kangaroo demo on solved puzzles #30 to #50 that have pubkeys, to show the sqrt speedup really works. Don't run it on unsolved ones.

## Experiments (22 Oct 2026)
See experiments/RESULTS.md for hidden-key falsification, kangaroo demo, and coverage anchors.
