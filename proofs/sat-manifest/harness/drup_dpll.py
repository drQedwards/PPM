"""Proof-emitting mirror of pmll three_sat.solve_3sat (commit 8e49955).

Same unit propagation, same branching heuristic (pick), same chronological
backtracking as three_sat.py. The only addition: at every conflict it emits the
clause that negates the current *unflipped* decision literals. Each such clause
is RUP (reverse unit propagation) with respect to the formula plus the lemmas
emitted before it, and the last lemma of a refutation is the empty clause. The
lemma list is therefore a DRUP (DRAT without deletions) proof that drat-trim
can check. The harness asserts that this mirror returns exactly the same
result dict as three_sat.solve_3sat on every instance, so the proof describes
the search that three_sat.py actually performs.
"""


def solve_with_proof(n, clauses):
    clauses = [list(c) for c in clauses]
    assign = [0] * (n + 1)
    trail = []
    nodes = decisions = units = conflicts = 0
    proof = []

    def val(lit):
        cur = assign[abs(lit)]
        if cur == 0:
            return 0
        return cur if lit > 0 else -cur

    def set_lit(lit):
        assign[abs(lit)] = 1 if lit > 0 else -1
        trail.append(lit)

    def undo_to(cp):
        while len(trail) > cp:
            assign[abs(trail.pop())] = 0

    def unit_propagate():
        nonlocal units
        changed = True
        while changed:
            changed = False
            for clause in clauses:
                sat = False
                open_count = 0
                open_lit = 0
                for lit in clause:
                    v = val(lit)
                    if v == 1:
                        sat = True
                        break
                    if v == 0:
                        open_count += 1
                        open_lit = lit
                if sat:
                    continue
                if open_count == 0:
                    return False
                if open_count == 1:
                    set_lit(open_lit)
                    units += 1
                    changed = True
        return True

    def satisfied():
        return all(any(val(l) == 1 for l in c) for c in clauses)

    def pick():
        count = [0] * (n + 1)
        for clause in clauses:
            csat = False
            ov = []
            for lit in clause:
                v = val(lit)
                if v == 1:
                    csat = True
                    break
                if v == 0:
                    ov.append(abs(lit))
            if csat:
                continue
            for x in ov:
                count[x] += 1
        best, best_count = 0, -1
        for x in range(1, n + 1):
            if assign[x] != 0:
                continue
            if count[x] > best_count:
                best, best_count = x, count[x]
        return best

    def pack(sat):
        a = [assign[x] == 1 for x in range(1, n + 1)] if sat else None
        return {"sat": sat, "assignment": a, "nodes": nodes, "decisions": decisions,
                "units": units, "conflicts": conflicts}, proof

    if not unit_propagate():
        conflicts += 1
        proof.append([])
        return pack(False)

    stack = []
    while True:
        nodes += 1
        if satisfied():
            return pack(True)
        x = pick()
        if x == 0:
            return pack(True)
        decisions += 1
        stack.append({"lit": x, "flipped": False, "checkpoint": len(trail)})
        set_lit(x)
        while not unit_propagate():
            conflicts += 1
            proof.append([-f["lit"] for f in stack if not f["flipped"]])
            flipped = False
            while stack:
                f = stack[-1]
                undo_to(f["checkpoint"])
                if not f["flipped"]:
                    f["flipped"] = True
                    set_lit(-f["lit"])
                    flipped = True
                    break
                stack.pop()
            if not flipped:
                return pack(False)
