"""The proof-emitting DPLL mirror must make exactly the search three_sat.py makes."""

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "sat_proof"))

from drup_dpll import solve_with_proof
from three_sat import UNSAT_CORE, solve_3sat


def _rup(clauses, lemma):
    """Reverse unit propagation: assigning the negation of lemma must reach a conflict."""
    assign = {}
    for lit in lemma:
        assign[abs(lit)] = lit < 0
    changed = True
    while changed:
        changed = False
        for clause in clauses:
            open_lits = []
            sat = False
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


def _check_drup(clauses, proof):
    db = [list(c) for c in clauses]
    for lemma in proof:
        assert _rup(db, lemma), lemma
        db.append(lemma)
    assert proof and proof[-1] == []


def test_mirror_matches_three_sat_and_proofs_are_rup():
    rng = random.Random(20261006)
    unsat = 0
    for n in (3, 5, 8, 12):
        for _ in range(25):
            m = round(4.26 * n)
            clauses = []
            for _ in range(m):
                vs = rng.sample(range(1, n + 1), 3)
                clauses.append([v if rng.random() < 0.5 else -v for v in vs])
            result, proof = solve_with_proof(n, clauses)
            assert result == solve_3sat(n, clauses)
            if not result["sat"]:
                unsat += 1
                _check_drup(clauses, proof)
    assert unsat > 0


def test_unsat_core_proof():
    result, proof = solve_with_proof(3, UNSAT_CORE)
    assert result == solve_3sat(3, UNSAT_CORE)
    assert result["sat"] is False
    _check_drup(UNSAT_CORE, proof)
    # Negative control: the empty clause alone is not RUP for the core.
    assert not _rup(UNSAT_CORE, [])


if __name__ == "__main__":
    test_mirror_matches_three_sat_and_proofs_are_rup()
    test_unsat_core_proof()
    print("ok")
