# SAT solvers in this repository

| File | What it decides | Method | Worst case | Checked by |
| --- | --- | --- | --- | --- |
| `two_sat.py` | 2-CNF | Implication graph + strongly connected components (Aspvall, Plass, Tarjan 1979) | O(n + m) | `tests/test_two_sat.py` (exhaustive search, n ≤ 10) |
| `xor_sat.py` | XOR-SAT | Gaussian elimination over GF(2) | polynomial | `tests/test_xor_sat.py` |
| `three_sat.py` | 3-CNF | DPLL with unit propagation | exponential | `tests/test_three_sat.py` (exhaustive search, n ≤ 10) |
| `SAT.py` | any CNF | CDCL: two watched literals, first-UIP learning, activity-based branching, phase saving, growing restarts. `use_clause_learning=False` gives plain DPLL | exponential | `tests/test_sat_py.py` (exhaustive search, n ≤ 10, both modes) |
| `SAT.pyx` | any CNF | The same CDCL / DPLL algorithm, compiled with Cython (C mode) | exponential | `tests/test_sat_pyx.py` (builds it; exhaustive search, n ≤ 10, both modes) |
| `SAT.c` / `SAT.h` | any CNF | Plain DPLL (`sat_solve`). Clause learning is declared in `SAT.h` but not implemented | exponential | no tests in this repo |

SAT and 3-SAT are NP-complete. Nothing here places them in P or says anything about P versus NP.

## SAT.py and SAT.pyx

- **Learning is sound.** Each learned clause comes from first-UIP conflict analysis: the conflict clause is resolved with the reasons of current-level literals until one current-level literal remains. That makes it a resolution consequence of the formula and earlier learned clauses. The tests check that every learned clause is RUP (reverse unit propagation) with respect to the formula and the clauses learned before it. On the build box, learned-clause sequences for UNSAT random 3-SAT instances (n = 20 to 125) were also accepted as DRAT proofs by drat-trim.
- **Answers are checked.** A SAT answer carries a value for every variable. Both solvers check it against the input clauses before returning it.
- **Limits.** Learned clauses are never deleted. Branching picks the most active unassigned variable by a linear scan. There is no preprocessing and no proof output. `max_conflicts` (default 10000 in SAT.py, 100000 in SAT.pyx) turns a long search into `TIMEOUT`.
- **SAT.py API.** `CNF`, `SATSolver(cnf, config).solve() -> (SATResult, model)` and `solve_sat` keep their signatures. Learned clauses stay in the solver (`SATSolver.learned_clauses()`); `cnf.clauses` is not modified. NumPy is only imported by the `Visualizer` helpers.
- **SAT.pyx API.** `CythonSATSolver(num_vars)` with `add_clause`, `solve() -> (code, model)`, `validate`, `get_stats`, `generate_ppm`, plus the `PySATSolver` wrapper. The result codes `SAT`, `UNSAT`, `UNKNOWN` and `TIMEOUT` are module-level ints. The configuration fields are writable attributes, so `PySATSolver(config=...)` works. It needs no C++ compiler and no NumPy.

## Building SAT.pyx

The extension module is named `SAT`. Build it outside the repository root, or it will shadow `SAT.py`:

```bash
pip install cython setuptools        # plus the Python headers, e.g. python3-dev
mkdir -p build/sat_pyx && cp SAT.pyx build/sat_pyx/
(cd build/sat_pyx && cythonize -i -3 SAT.pyx)
```

`tests/test_sat_pyx.py` does the same in a temporary directory. When Cython, setuptools, the Python headers or a C compiler are missing, it skips. The CI workflow does not install Cython, so CI skips this test unless Cython happens to be present.

## Timing

Measured on one machine. These numbers are not a general performance claim.

- Machine: Intel(R) Xeon(R) Processor (8 vCPUs, the build box), Linux x86_64, Python 3.13.5, Cython 3.3.0, gcc 14.2.0 (default `-O2` from `cythonize -i`).
- Instances: uniform random 3-SAT, clause/variable ratio 4.26, seed 20261007, 10 instances per n.
- Method: one single-threaded run per solver per instance, wall time with `time.perf_counter`, including loading the clauses. Every SAT answer was checked, and all solvers agreed on every decision.
- Coverage: three_sat.py and SAT.py DPLL were skipped above n = 75, and SAT.pyx DPLL above n = 100.

| n | SAT/UNSAT | three_sat.py (DPLL) | SAT.py CDCL | SAT.py DPLL | SAT.pyx CDCL | SAT.pyx DPLL |
|---|---|---|---|---|---|---|
| 50 | 8/2 | 12.6 ms | 2.8 ms | 7.9 ms | 0.2 ms | 0.3 ms |
| 75 | 3/7 | 138.9 ms | 20.4 ms | 227.2 ms | 0.9 ms | 5.4 ms |
| 100 | 5/5 | skipped | 36.9 ms | skipped | 1.2 ms | 21.5 ms |
| 150 | 4/6 | skipped | 537.9 ms | skipped | 10.8 ms | skipped |

Cells are the median time per instance. On this set, SAT.pyx CDCL had a median roughly 14x (n = 50) to 50x (n = 150) lower than SAT.py CDCL. Clause learning mattered more than compilation as n grew. The times grow quickly with n, as expected for an exponential worst case.

Reproduce: `python tools/sat_bench/bench_solvers.py PATH/TO/SAT.cpython-*.so`.
