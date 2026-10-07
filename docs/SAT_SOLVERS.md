# SAT solvers in this repository

| File | What it decides | Method | Worst case | Checked by |
| --- | --- | --- | --- | --- |
| `two_sat.py` | 2-CNF | Implication graph + strongly connected components (Aspvall, Plass, Tarjan 1979) | O(n + m) | `tests/test_two_sat.py` (exhaustive search, n ≤ 10) |
| `xor_sat.py` | XOR-SAT | Gaussian elimination over GF(2) | polynomial | `tests/test_xor_sat.py` |
| `three_sat.py` | 3-CNF | DPLL with unit propagation | exponential | `tests/test_three_sat.py` (exhaustive search, n ≤ 10) |
| `SAT.py` | any CNF | CDCL: two watched literals, first-UIP learning, activity-based branching, phase saving, growing restarts. `use_clause_learning=False` gives plain DPLL | exponential | `tests/test_sat_py.py` (exhaustive search, n ≤ 10, both modes) |
| `SAT.pyx` | any CNF | The same CDCL / DPLL algorithm, compiled with Cython (C mode) | exponential | `tests/test_sat_pyx.py` (builds it; exhaustive search, n ≤ 10, both modes) |
| `SAT.c` / `SAT.h` | any CNF | The same CDCL / DPLL algorithm in C (`sat_solve`; `use_clause_learning = false` gives plain DPLL), with optional DRUP proof output | exponential | `tests/test_sat_c.py` (compiles it with the system C compiler; exhaustive search, n ≤ 10, both modes; DRUP lines checked by RUP) |

SAT and 3-SAT are NP-complete. Nothing here places them in P or says anything about P versus NP.

SAT.c is a standalone library and example program. It is not wired into PPM's dependency resolution.

## SAT.py, SAT.pyx and SAT.c

- **Learning is sound.** Each learned clause comes from first-UIP conflict analysis: the conflict clause is resolved with the reasons of current-level literals until one current-level literal remains. That makes it a resolution consequence of the formula and earlier learned clauses. The tests check that every learned clause is RUP (reverse unit propagation) with respect to the formula and the clauses learned before it. On the build box, learned-clause sequences for UNSAT random 3-SAT instances (n = 20 to 125) were also accepted as DRAT proofs by drat-trim, and so were SAT.c's DRUP proofs for 68 UNSAT runs (the 20 UNSAT instances of the timing set below in CDCL mode and the 14 with n ≤ 100 in DPLL mode, pigeonhole PHP(6,5) and PHP(7,6) in both modes, and the 15 UNSAT instances of the proof manifest in both modes). drat-trim is not run in CI.
- **Answers are checked.** A SAT answer carries a value for every variable. All three solvers check it against the input clauses before returning it.
- **Limits.** Learned clauses are never deleted. Branching picks the most active unassigned variable by a linear scan. There is no preprocessing. Only SAT.c writes proofs. `max_conflicts` (default 10000 in SAT.py, 100000 in SAT.pyx; in SAT.c 0 means no limit, which is the default, and `sat_minisat_config()` uses 100000) turns a long search into `TIMEOUT` (`SAT_ERROR_TIMEOUT` in C).
- **SAT.py API.** `CNF`, `SATSolver(cnf, config).solve() -> (SATResult, model)` and `solve_sat` keep their signatures. Learned clauses stay in the solver (`SATSolver.learned_clauses()`); `cnf.clauses` is not modified. NumPy is only imported by the `Visualizer` helpers.
- **SAT.pyx API.** `CythonSATSolver(num_vars)` with `add_clause`, `solve() -> (code, model)`, `validate`, `get_stats`, `generate_ppm`, plus the `PySATSolver` wrapper. The result codes `SAT`, `UNSAT`, `UNKNOWN` and `TIMEOUT` are module-level ints. The configuration fields are writable attributes, so `PySATSolver(config=...)` works. It needs no C++ compiler and no NumPy.
- **SAT.c API.** Everything `SAT.h` declared before keeps its signature, and the functions that were declared but missing are now implemented (`cnf_copy`, `cnf_simplify`, `cnf_parse_string`, `cnf_write_dimacs`, `sat_solve_with_assumptions`, `dpll_with_learning`, `analyze_conflict`, `restart`, `validate_solution`, `generate_implication_graph`, and the rest). `SAT.h` gained one field at the end of `SATSolver` (`internal`, the solver's private state) and one function, `sat_set_proof_output(solver, FILE*)`, which writes each learned clause and, on UNSAT, the empty clause in DRUP format (in DPLL mode it writes, at each conflict, the clause that negates the open decisions). `cnf_add_clause` still rejects an empty clause and now also rejects literals outside `1..num_vars`; `cnf_add_clause_array` and `cnf_parse_dimacs` accept the empty clause. `sat_default_config()` now enables clause learning and has no conflict limit, so `sat_solve` always decides. `sat_glucose_config()` is the same algorithm with different parameters, not Glucose. `pure_literal_elimination` is a helper that `sat_solve` does not call, because a pure literal is not implied by the formula. The DIMACS parser reads clauses that span lines, comment lines and the SATLIB `%` end marker, and rejects out-of-range literals. Compile with `-DSAT_NO_MAIN` to leave out the example `main`.

## Building SAT.pyx

The extension module is named `SAT`. Build it outside the repository root, or it will shadow `SAT.py`:

```bash
pip install cython setuptools        # plus the Python headers, e.g. python3-dev
mkdir -p build/sat_pyx && cp SAT.pyx build/sat_pyx/
(cd build/sat_pyx && cythonize -i -3 SAT.pyx)
```

`tests/test_sat_pyx.py` does the same in a temporary directory. When Cython, setuptools, the Python headers or a C compiler are missing, it skips. The "Resolve & Lock (SAT) + Doctor (explain)" job in `.github/workflows/ppm-ci.yml` installs Cython and setuptools, so it builds and runs this test. The other workflows that run pytest do not install Cython and skip it.

## Building and testing SAT.c

```bash
cc -O2 -o sat SAT.c -lm                       # example program: ./sat [file.cnf]
cc -O2 -DSAT_NO_MAIN -I. SAT.c tests/sat_c_driver.c -o sat_c_driver -lm
```

`tests/test_sat_c.py` compiles SAT.c with `tests/sat_c_driver.c` in a temporary directory, runs the API checks, and compares 1,100 random CNFs with n ≤ 10 (600 in CDCL mode, 200 in CDCL mode with a restart after every conflict, 300 in DPLL mode; both SAT and UNSAT) against exhaustive search. It checks every witness and checks every DRUP line by reverse unit propagation, including the final empty clause on UNSAT. It also checks 20 random 3-SAT instances with n = 40 against SAT.py. It skips when no C compiler is found (`CC`, `cc`, `gcc` or `clang`); CI runners have gcc. `SAT_C_CFLAGS` adds compiler flags. On the build box the test also passed with `SAT_C_CFLAGS="-fsanitize=address,undefined -fno-sanitize-recover=all"`, with LeakSanitizer on and no reports.

## Timing

Measured on one machine. These numbers are not a general performance claim.

- Machine: Intel(R) Xeon(R) Processor (8 vCPUs, the build box), Linux x86_64, Python 3.13.5, Cython 3.3.0, gcc 14.2.0 (default `-O2` from `cythonize -i`; SAT.c built with `cc -O2 -shared -fPIC`).
- Instances: uniform random 3-SAT, clause/variable ratio 4.26, seed 20261007, 10 instances per n.
- Method: one single-threaded run per solver per instance, wall time with `time.perf_counter`, including loading the clauses. SAT.c is called through ctypes, so its time includes one ctypes call per clause. Every SAT answer was checked, and all solvers agreed on every decision.
- Coverage: three_sat.py and SAT.py DPLL were skipped above n = 75, and SAT.pyx DPLL and SAT.c DPLL above n = 100.
- All columns come from one run of the script (2026-10-06).

| n | SAT/UNSAT | three_sat.py (DPLL) | SAT.py CDCL | SAT.py DPLL | SAT.pyx CDCL | SAT.pyx DPLL | SAT.c CDCL | SAT.c DPLL |
|---|---|---|---|---|---|---|---|---|
| 50 | 8/2 | 12.1 ms | 2.8 ms | 8.0 ms | 0.2 ms | 0.3 ms | 0.3 ms | 0.3 ms |
| 75 | 3/7 | 139.9 ms | 18.8 ms | 220.6 ms | 0.9 ms | 5.5 ms | 0.9 ms | 1.2 ms |
| 100 | 5/5 | skipped | 33.8 ms | skipped | 1.2 ms | 20.5 ms | 1.7 ms | 7.3 ms |
| 150 | 4/6 | skipped | 514.3 ms | skipped | 10.6 ms | skipped | 12.2 ms | skipped |

Cells are the median time per instance. On this set, SAT.pyx CDCL had a median roughly 14x (n = 50) to 49x (n = 150) lower than SAT.py CDCL, and SAT.c CDCL was within about 1.5x of SAT.pyx CDCL. SAT.c DPLL was faster than SAT.pyx DPLL here; one known difference is that SAT.c's `cnf_add_clause` seeds variable activity (+0.01 per positive occurrence, as it did before), so the two start with a different branching order. Clause learning mattered more than compilation as n grew. The times grow quickly with n, as expected for an exponential worst case.

Reproduce: `python tools/sat_bench/bench_solvers.py PATH/TO/SAT.cpython-*.so` (it compiles SAT.c itself with `cc`, or `CC` if set).
