# Published SAT proof-of-computation manifest

These are the files behind the draft manifest described in [`docs/SAT-PROOF-MANIFEST.md`](../../docs/SAT-PROOF-MANIFEST.md). With them, anyone can recompute the Merkle root

```
723cbe658e875821ac2fbb5cd8bfd6937f3a61a1aba7e6665aa6ae5e2c6e6078
```

from this repository alone.

This is a record of finite computations by `two_sat.py` and `three_sat.py` on 427 small benchmark instances, with a certificate for every answer. It is not a proof that P = NP, and not a proof that P ≠ NP; P versus NP is open.

| Path | What it is |
| --- | --- |
| `manifest.json` | The manifest (schema `pmll-sat-proof-manifest/v0-draft`, generated 2026-10-06T22:02:59-04:00) |
| `merkle_leaves.json` | Leaf order and leaf hashes (455 leaves), referenced by `manifest.merkle.leaf_order_file` |
| `instances/*.cnf` | The 427 DIMACS instances, each hashed in the manifest |
| `proofs/*.drat` | DRUP proofs (DRAT text format) for the 15 UNSAT instances |
| `harness/build_manifest.py`, `harness/drup_dpll.py` | The harness scripts whose sha256 is recorded under `sources.harness`, published byte-for-byte as they ran (their absolute paths point at the original build machine) |
| `SHA256SUMS` | sha256 of every file above, for a quick `sha256sum -c` |

The files are byte-identical in drQedwards/pmll and drQedwards/PPM.

## Verify

From the repository root:

```bash
python tools/sat_proof/verify_manifest.py proofs/sat-manifest \
  --expect-root 723cbe658e875821ac2fbb5cd8bfd6937f3a61a1aba7e6665aa6ae5e2c6e6078
```

The full check needs [drat-trim](https://github.com/marijnheule/drat-trim) (`$DRAT_TRIM`, `PATH`, or `proofs/sat-manifest/tools/drat-trim/drat-trim`). The manifest was built with commit `2e3b2dc0ecf938addbd779d42877b6ed69d9a985`, compiled with `gcc drat-trim.c -O2`:

```bash
git clone https://github.com/marijnheule/drat-trim /tmp/drat-trim
git -C /tmp/drat-trim checkout 2e3b2dc0ecf938addbd779d42877b6ed69d9a985
gcc -O2 -o /tmp/drat-trim/drat-trim /tmp/drat-trim/drat-trim.c
DRAT_TRIM=/tmp/drat-trim/drat-trim python tools/sat_proof/verify_manifest.py proofs/sat-manifest \
  --expect-root 723cbe658e875821ac2fbb5cd8bfd6937f3a61a1aba7e6665aa6ae5e2c6e6078
```

Without drat-trim, add `--hash-only`: the root, every file hash and every SAT witness are still checked, but UNSAT proofs are only hash-checked, and the result line says the check was partial. `tests/test_sat_manifest.py` runs that hash-only check in CI.

The root stored inside `manifest.json` only shows the files agree with each other. Compare against the root published above (or anchored on-chain later). The manifest's `status` field reads `DRAFT - not anchored` and stays that way: it is part of the hashed header, so changing it would change the root.
