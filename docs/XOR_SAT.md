# XOR-SAT by Gaussian elimination over GF(2)

`xor_sat.py` decides systems of XOR equations

```
x_{i1} ⊕ x_{i2} ⊕ … ⊕ x_{ik} = b,    b ∈ {0, 1}
```

over Boolean variables `x_1 … x_n`. Over the two-element field GF(2) this is a linear system `A x = b`, so Gaussian elimination decides it exactly.

## What it returns

```python
from xor_sat import solve_xorsat, verifies, verify_certificate

eqs = [([1, 2], 1), ([2, 3], 1), ([1, 3], 1)]   # (variables, rhs); variables are 1-based
r = solve_xorsat(3, eqs)
# r["sat"] is False; r["certificate"] == [0, 1, 2]
assert verify_certificate(3, eqs, r["certificate"])
```

- **SAT**: `assignment` is a witness (free variables set to 0, pivot variables read off the reduced rows). `verifies(n, eqs, assignment)` checks it directly.
- **UNSAT**: `certificate` is a list of equation indices whose XOR is `0 = 1`. Any assignment satisfying all equations would satisfy their XOR, and nothing satisfies `0 = 1`, so the certificate proves unsatisfiability. `verify_certificate` checks it with one linear pass over the named equations; it does not trust the solver.
- `rank`, `pivots`, and `ops` (row XORs plus pivot probes) / `row_xors` are reported for every run. When SAT, the system has exactly `2^(n - rank)` solutions.

## How

Each equation is one Python int: bit `v - 1` is the coefficient of `x_v`, bit `n` is the right-hand side. Repeated variables cancel (`x ⊕ x = 0`). A second int per row records which original equations have been XORed into it; that history becomes the UNSAT certificate when a row reduces to all-zero coefficients with right-hand side 1. Elimination goes to reduced row echelon form, so back-substitution is a single read per pivot.

## Complexity

With `n` variables, `m` equations, and `w`-bit machine words, each row XOR touches about `(n + 1) / w` words of coefficients, and there are at most `rank · m ≤ min(n, m) · m` row XORs. That is **O(n² m / w)** for the elimination itself. Carrying the certificate history widens each row by `m` bits, giving O(n m (n + m) / w) in total, the same order when `m = O(n)`. Python ints do the word-parallel XOR.

## What this is not

XOR-SAT (affine Boolean constraints) is a known polynomial-time case. It is one of the tractable classes in Schaefer's dichotomy theorem (1978), alongside 2-SAT, Horn-SAT, and dual-Horn-SAT. Solving it efficiently is textbook linear algebra.

- This is **not** progress on P versus NP.
- It does **not** solve 3-SAT or general CNF. A 3-clause `(a ∨ b ∨ c)` is not an XOR constraint, and translating CNF into XOR equations does not preserve satisfiability in general.
- There is **no** link to the Hodge conjecture or any other open problem.

Where `two_sat.py` is present (drQedwards/pmll), it is the other polynomial Schaefer case in this tree: 2-SAT via implication-graph SCCs. The general CDCL solver in `SAT.h` / `SAT.py` remains the route for arbitrary CNF, with no polynomial bound.

## Tests

```bash
python tests/test_xor_sat.py      # or: pytest tests/test_xor_sat.py
```

`tests/test_xor_sat.py` builds 1,200 random systems with n from 1 to 10: planted (always consistent), uniformly random, and forced-inconsistent (a random subset's XOR added with its right-hand side flipped). For each one it enumerates all `2^n` assignments and checks that the SAT/UNSAT status agrees, every witness satisfies the system, every UNSAT certificate XORs to `0 = 1`, and the brute-force solution count equals `2^(n - rank)`. It also checks edge cases (empty system, `0 = 1`, cancelling repeats) and that `verify_certificate` rejects empty, partial, duplicated, out-of-range, and consistent-subset certificates.
