"""Linear 2-SAT decision procedure.

Aspvall, Plass, and Tarjan (1979): each width-2 clause (a ∨ b) is the pair of
implications (¬a → b) and (¬b → a). The formula is satisfiable exactly when no
variable shares a strongly connected component with its negation. Kosaraju's
algorithm finds those components in time linear in variables plus clauses.

This decides 2-SAT. It does not decide 3-SAT, and it is not a resolution of
P versus NP.
"""

from __future__ import annotations

def _node(lit: int) -> int:
    variable = abs(lit) - 1
    return variable * 2 if lit > 0 else variable * 2 + 1


def solve_2sat(n: int, clauses: list[tuple[int, int]]) -> dict:
    size = n * 2
    adj: list[list[int]] = [[] for _ in range(size)]
    rev: list[list[int]] = [[] for _ in range(size)]
    implications: list[tuple[int, int]] = []
    ops = 0

    for a, b in clauses:
        na, nb = _node(a), _node(b)
        adj[na ^ 1].append(nb)
        rev[nb].append(na ^ 1)
        adj[nb ^ 1].append(na)
        rev[na].append(nb ^ 1)
        implications.append((-a, b))
        implications.append((-b, a))
        ops += 4

    seen = [False] * size
    order: list[int] = []

    def dfs1(start: int) -> None:
        nonlocal ops
        stack = [start]
        frame = [0]
        seen[start] = True
        ops += 1
        while stack:
            u = stack[-1]
            edges = adj[u]
            i = frame[-1]
            pushed = False
            while i < len(edges):
                v = edges[i]
                i += 1
                ops += 1
                if not seen[v]:
                    seen[v] = True
                    ops += 1
                    frame[-1] = i
                    stack.append(v)
                    frame.append(0)
                    pushed = True
                    break
            if not pushed:
                frame[-1] = i
                order.append(u)
                stack.pop()
                frame.pop()

    for node in range(size):
        if not seen[node]:
            dfs1(node)

    comp = [-1] * size
    components = 0

    def dfs2(start: int, ident: int) -> None:
        nonlocal ops
        stack = [start]
        comp[start] = ident
        ops += 1
        while stack:
            u = stack.pop()
            for v in rev[u]:
                ops += 1
                if comp[v] < 0:
                    comp[v] = ident
                    ops += 1
                    stack.append(v)

    for index in range(len(order) - 1, -1, -1):
        node = order[index]
        if comp[node] < 0:
            dfs2(node, components)
            components += 1

    assignment: list[bool] = []
    for variable in range(n):
        yes = comp[variable * 2]
        no = comp[variable * 2 + 1]
        ops += 1
        if yes == no:
            return {
                "sat": False,
                "assignment": None,
                "ops": ops,
                "components": components,
                "conflict": variable,
                "implications": implications,
            }
        assignment.append(yes > no)

    return {
        "sat": True,
        "assignment": assignment,
        "ops": ops,
        "components": components,
        "conflict": None,
        "implications": implications,
    }


def verifies(n: int, clauses: list[tuple[int, int]], assignment: list[bool]) -> bool:
    del n
    for a, b in clauses:
        left = assignment[a - 1] if a > 0 else not assignment[-a - 1]
        right = assignment[b - 1] if b > 0 else not assignment[-b - 1]
        if not (left or right):
            return False
    return True
