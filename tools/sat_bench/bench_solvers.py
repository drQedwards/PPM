#!/usr/bin/env python3
"""Time three_sat.py, SAT.py and a built SAT.pyx on uniform random 3-SAT.

Usage: python tools/sat_bench/bench_solvers.py PATH_TO_BUILT_SAT_EXTENSION [--sizes 50,75,100,150] [--per 10]

Instances: uniform random 3-SAT, clause/variable ratio 4.26, three distinct
variables per clause, random signs, seed 20261007, ``--per`` instances per n.
Each solver runs each instance once, single-threaded, timed with
time.perf_counter. Every SAT answer is checked against the formula, and all
solvers must agree on SAT/UNSAT. three_sat.py is skipped above n = 75 because
its unit propagation rescans every clause.
"""
import importlib.util
import platform
import random
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import SAT as satpy  # noqa: E402
from three_sat import solve_3sat  # noqa: E402


def load_ext(path):
    spec = importlib.util.spec_from_file_location("SAT", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def instances(sizes, per):
    rng = random.Random(20261007)
    for n in sizes:
        for _ in range(per):
            m = round(4.26 * n)
            yield n, [[v if rng.random() < 0.5 else -v for v in rng.sample(range(1, n + 1), 3)] for _ in range(m)]


def main():
    ext = load_ext(sys.argv[1])
    sizes, per = [50, 75, 100, 150], 10
    if "--sizes" in sys.argv:
        sizes = [int(x) for x in sys.argv[sys.argv.index("--sizes") + 1].split(",")]
    if "--per" in sys.argv:
        per = int(sys.argv[sys.argv.index("--per") + 1])

    def run_py(n, cl, learn):
        cnf = satpy.CNF(n)
        for c in cl:
            cnf.add_clause(c)
        r, model = satpy.SATSolver(cnf, {"use_clause_learning": learn, "max_conflicts": 10 ** 9}).solve()
        return r is satpy.SATResult.SATISFIABLE, model

    def run_pyx(n, cl, learn):
        s = ext.CythonSATSolver(n)
        s.use_clause_learning = learn
        s.max_conflicts = 2 ** 31 - 1
        for c in cl:
            s.add_clause(c)
        r, model = s.solve()
        return r == ext.SAT, model

    def run_three(n, cl):
        r = solve_3sat(n, cl)
        return r["sat"], (None if not r["sat"] else {i + 1: v for i, v in enumerate(r["assignment"])})

    solvers = {
        "three_sat.py (DPLL)": lambda n, cl: run_three(n, cl) if n <= 75 else None,
        "SAT.py CDCL": lambda n, cl: run_py(n, cl, True),
        "SAT.py DPLL": lambda n, cl: run_py(n, cl, False) if n <= 75 else None,
        "SAT.pyx CDCL": lambda n, cl: run_pyx(n, cl, True),
        "SAT.pyx DPLL": lambda n, cl: run_pyx(n, cl, False) if n <= 100 else None,
    }
    times = {(name, n): [] for name in solvers for n in sizes}
    answers = {n: [0, 0] for n in sizes}
    for n, cl in instances(sizes, per):
        decided = set()
        for name, fn in solvers.items():
            t0 = time.perf_counter()
            out = fn(n, cl)
            dt = time.perf_counter() - t0
            if out is None:
                continue
            sat, model = out
            if sat:
                assert all(any((model[abs(l)] if l > 0 else not model[abs(l)]) for l in c) for c in cl), name
            decided.add(sat)
            times[(name, n)].append(dt)
        assert len(decided) == 1, "solvers disagree"
        answers[n][0 if decided.pop() else 1] += 1

    cpu = "unknown"
    try:
        cpu = next(l.split(":", 1)[1].strip() for l in open("/proc/cpuinfo") if l.startswith("model name"))
    except (OSError, StopIteration):
        pass
    try:
        import Cython
        cython_version = Cython.__version__
    except ImportError:
        cython_version = "unknown"
    import sysconfig
    print(f"Machine: {cpu}; {platform.system()} {platform.machine()}; Python {platform.python_version()}; "
          f"Cython {cython_version}; CC {sysconfig.get_config_var('CC')}")
    print(f"Instances: uniform random 3-SAT, ratio 4.26, seed 20261007, {per} per n")
    print()
    print("| n | SAT/UNSAT | " + " | ".join(solvers) + " |")
    print("|---|---|" + "---|" * len(solvers))
    for n in sizes:
        cells = []
        for name in solvers:
            ts = times[(name, n)]
            cells.append(f"{statistics.median(ts) * 1000:.1f} ms" if ts else "skipped")
        print(f"| {n} | {answers[n][0]}/{answers[n][1]} | " + " | ".join(cells) + " |")
    print()
    print("Cells: median wall time per instance (one run each).")


if __name__ == "__main__":
    main()
