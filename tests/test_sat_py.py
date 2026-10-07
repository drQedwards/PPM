"""SAT.py against exhaustive search for n <= 10, in CDCL and plain-DPLL modes."""

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import SAT  # noqa: E402
from SAT import CNF, SATResult, SATSolver, solve_sat  # noqa: E402


def brute(n, clauses):
    for mask in range(1 << n):
        a = [((mask >> i) & 1) == 1 for i in range(n)]
        if all(any((a[l - 1] if l > 0 else not a[-l - 1]) for l in c) for c in clauses):
            return a
    return None


def satisfies(clauses, model):
    return all(any((model[abs(l)] if l > 0 else not model[abs(l)]) for l in c) for c in clauses)


def rup(db, lemma):
    """Reverse unit propagation: assigning the negation of lemma reaches a conflict."""
    assign = {}
    for lit in lemma:
        assign[abs(lit)] = lit < 0
    changed = True
    while changed:
        changed = False
        for clause in db:
            open_lits, sat = [], False
            for lit in clause:
                v = assign.get(abs(lit))
                if v is None:
                    open_lits.append(lit)
                elif v == (lit > 0):
                    sat = True
                    break
            if sat:
                continue
            if not open_lits:
                return True
            if len(open_lits) == 1:
                assign[abs(open_lits[0])] = open_lits[0] > 0
                changed = True
    return False


def random_cnf(rng, n, m, kmax):
    clauses = []
    for _ in range(m):
        k = rng.randint(1, min(kmax, n))
        vs = rng.sample(range(1, n + 1), k)
        clauses.append([v if rng.random() < 0.5 else -v for v in vs])
    return clauses


def build(n, clauses):
    cnf = CNF(n)
    for c in clauses:
        cnf.add_clause(c)
    return cnf


def check(n, clauses, config):
    solver = SATSolver(build(n, clauses), config)
    result, model = solver.solve()
    truth = brute(n, clauses)
    if truth is None:
        assert result is SATResult.UNSATISFIABLE, (n, clauses, result)
        assert model is None
    else:
        assert result is SATResult.SATISFIABLE, (n, clauses, result)
        assert sorted(model) == list(range(1, n + 1))
        assert satisfies(clauses, model)
        assert solver.validate_solution()
    db = [list(c) for c in clauses]
    for lemma in solver.learned_clauses():
        assert rup(db, lemma), (clauses, lemma)
        db.append(lemma)
    return result


def test_against_brute_force_cdcl_and_dpll():
    rng = random.Random(20261007)
    counts = {SATResult.SATISFIABLE: 0, SATResult.UNSATISFIABLE: 0}
    configs = [
        {},
        {"restart_interval": 2},
        {"use_clause_learning": False},
        {"use_vsids": False, "use_phase_saving": False},
    ]
    for n in range(1, 11):
        for _ in range(30):
            ratio = rng.choice([2.0, 3.5, 4.3, 5.5, 7.0])
            clauses = random_cnf(rng, n, max(1, int(ratio * n)), 3)
            for config in configs:
                counts[check(n, clauses, config)] += 1
    assert counts[SATResult.SATISFIABLE] > 100
    assert counts[SATResult.UNSATISFIABLE] > 100


def test_wider_clauses_against_brute_force():
    rng = random.Random(7)
    for n in range(4, 11):
        for _ in range(15):
            clauses = random_cnf(rng, n, rng.randint(n, 12 * n), 5)
            check(n, clauses, {})
            check(n, clauses, {"use_clause_learning": False})


def test_edge_cases():
    all_signs = [[a * 1, b * 2, c * 3] for a in (1, -1) for b in (1, -1) for c in (1, -1)]
    assert check(3, all_signs, {}) is SATResult.UNSATISFIABLE
    assert check(3, all_signs, {"use_clause_learning": False}) is SATResult.UNSATISFIABLE
    assert check(4, [], {}) is SATResult.SATISFIABLE
    assert check(2, [[1], [-1]], {}) is SATResult.UNSATISFIABLE
    assert check(3, [[1, 1, -2], [2, 2], [-1, 3, 3]], {}) is SATResult.SATISFIABLE
    assert check(2, [[1, -1], [2]], {}) is SATResult.SATISFIABLE
    cnf = CNF(2)
    cnf.add_clause([])
    assert solve_sat(cnf)[0] is SATResult.UNSATISFIABLE
    cnf = CNF(1)
    try:
        cnf.add_clause([2])
    except ValueError:
        pass
    else:
        raise AssertionError("out-of-range literal accepted")


def test_does_not_mutate_input_and_solves_twice():
    rng = random.Random(3)
    clauses = random_cnf(rng, 10, 45, 3)
    cnf = build(10, clauses)
    before = [[l.var for l in c.literals] for c in cnf.clauses]
    solver = SATSolver(cnf)
    first = solver.solve()
    second = solver.solve()
    assert first[0] == second[0]
    assert [[l.var for l in c.literals] for c in cnf.clauses] == before


def test_timeout():
    # Pigeonhole 7 -> 6 is UNSAT and needs many conflicts.
    p, h = 7, 6
    var = lambda i, j: i * h + j + 1
    clauses = [[var(i, j) for j in range(h)] for i in range(p)]
    clauses += [[-var(i, j), -var(k, j)] for j in range(h) for i in range(p) for k in range(i + 1, p)]
    result, model = SATSolver(build(p * h, clauses), {"max_conflicts": 5}).solve()
    assert result is SATResult.TIMEOUT and model is None


def test_dimacs_round_trip(tmp_path):
    path = tmp_path / "f.cnf"
    path.write_text("c comment\np cnf 3 3\n1 -2\n 0 2 3 0\nc mid comment\n-1 -3 0\n")
    cnf = CNF.from_dimacs(str(path))
    assert [[l.var for l in c.literals] for c in cnf.clauses] == [[1, -2], [2, 3], [-1, -3]]
    out = tmp_path / "g.cnf"
    cnf.to_dimacs(str(out))
    again = CNF.from_dimacs(str(out))
    assert [[l.var for l in c.literals] for c in again.clauses] == [[1, -2], [2, 3], [-1, -3]]
    assert solve_sat(cnf)[0] is SATResult.SATISFIABLE


def test_module_has_no_import_time_numpy_dependency():
    assert "np" not in vars(SAT)


if __name__ == "__main__":
    import tempfile
    test_against_brute_force_cdcl_and_dpll()
    test_wider_clauses_against_brute_force()
    test_edge_cases()
    test_does_not_mutate_input_and_solves_twice()
    test_timeout()
    with tempfile.TemporaryDirectory() as d:
        test_dimacs_round_trip(Path(d))
    test_module_has_no_import_time_numpy_dependency()
    print("ok")
