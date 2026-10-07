# 3-SAT is decided exactly, not in polynomial time

`two_sat.py` decides width-2 formulas from implication-graph components, in time linear in n + m. That construction stops at width 2. A clause `(a ∨ b ∨ c)` is not a pair of implications.

`three_sat.py` decides 3-CNF by DPLL with unit propagation. It returns a satisfying assignment, or unsatisfiable after the search tree is exhausted. The running time is exponential in the worst case, and no polynomial bound is known. Nothing in this file places 3-SAT in P.

`SAT.c` / `SAT.h` remain the general-width solver. `sat_solve` is plain DPLL; clause learning is declared in `SAT.h` but not implemented. `SAT.py` is experimental and currently fails on its first solve (see `docs/TWO_SAT.md`). Use `three_sat.py` when you want the small checked decider that matches family 002 in [drQedwards/math](https://github.com/drQedwards/math).

```bash
python tests/test_three_sat.py
```

The test enumerates all assignments for n ≤ 10.
