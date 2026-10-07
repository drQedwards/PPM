# Linear 2-SAT, beside the general SAT solver

`SAT.py` and `SAT.pyx` are general-width CDCL solvers (two watched literals, first-UIP clause learning, restarts), checked against exhaustive search for n ≤ 10. `SAT.c` / `SAT.h` are a general-width solver whose `sat_solve` runs plain DPLL; clause learning is declared in `SAT.h` but not implemented in `SAT.c`. None of these is a polynomial-time bound; the worst case is exponential. See [`SAT_SOLVERS.md`](SAT_SOLVERS.md).

`two_sat.py` is a different procedure, and only for clauses of width two. Each clause `(a ∨ b)` becomes the implications `(¬a → b)` and `(¬b → a)`. Strongly connected components of that graph decide the formula in time linear in variables plus clauses (Aspvall, Plass, Tarjan, 1979). A variable set true when its component index outranks the component of its negation is a satisfying assignment, unless some variable shares a component with its negation.

Use it when every clause the silo is asked to decide has two literals. Do not route 3-CNF instances through it. The SAT bridge in `PMLL.c` (`sat_bridge_*`) still maps general tokens; this file does not replace that bridge and does not change `init_pml`.

The same procedure, the brute-force check, and the note that this is not a P versus NP result live in [drQedwards/math](https://github.com/drQedwards/math), family 001.

```bash
python tests/test_two_sat.py
```

The test enumerates all assignments for n ≤ 10 and compares status and witnesses.
