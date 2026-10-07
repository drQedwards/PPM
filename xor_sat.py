"""XOR-SAT by Gaussian elimination over GF(2).

An XOR-SAT instance is a system of equations

    x_{i1} xor x_{i2} xor ... xor x_{ik} = b        (b in {0, 1})

over Boolean variables x_1 .. x_n. Over the field GF(2) that is a linear
system A x = b, so Gaussian elimination decides it.

Each equation is packed into one Python int: bit (v - 1) is the coefficient of
x_v and bit n is the right-hand side. Alongside each row the solver keeps a
second int whose bit j is set when original equation j has been XORed into the
row. Eliminating to reduced row echelon form then gives:

* SAT: set every free variable to 0 and read each pivot variable off its row.
* UNSAT: some row reduces to 0 = 1. Its history bits name a set of original
  equations whose XOR is 0 = 1. Anyone can check that certificate with a
  linear pass (see ``verify_certificate``); no trust in the solver is needed.

Cost: with w-bit machine words, each row XOR touches about (n + 1 + m) / w
words, and there are at most rank * m of them, rank <= min(n, m). That is
O(n^2 m / w) for the coefficient part and O(n m (n + m) / w) including the
certificate history, which is the same order when m = O(n).

XOR-SAT is one of Schaefer's (1978) polynomial-time cases of Boolean
constraint satisfaction. Solving it says nothing about 3-SAT and is not
progress on P versus NP.
"""

from __future__ import annotations

Equation = tuple[list[int], int]


def _popcount(x: int) -> int:
    return bin(x).count("1")


def pack(n: int, variables: list[int], rhs: int) -> int:
    """Pack one equation into an int; repeated variables cancel (x xor x = 0)."""
    row = 0
    for v in variables:
        if not 1 <= v <= n:
            raise ValueError(f"variable {v} out of range 1..{n}")
        row ^= 1 << (v - 1)
    if rhs not in (0, 1):
        raise ValueError(f"rhs must be 0 or 1, got {rhs!r}")
    return row | (rhs << n)


def solve_xorsat(n: int, equations: list[Equation]) -> dict:
    """Decide a system of XOR equations over variables 1..n.

    Returns a dict with:
      sat          True or False
      assignment   list[bool] of length n when sat, else None
      certificate  sorted list of equation indices whose XOR is 0 = 1 when
                   unsat, else None
      rank         rank of the coefficient matrix A
      pivots       pivot variable (1-based) for each independent row
      ops          row XORs plus pivot probes performed
      row_xors     row XORs alone
    """
    rows = [pack(n, vs, b) for vs, b in equations]
    history = [1 << j for j in range(len(rows))]
    m = len(rows)
    coeff_mask = (1 << n) - 1
    ops = 0
    row_xors = 0
    pivots: list[int] = []

    r = 0
    for col in range(n):
        bit = 1 << col
        pivot = -1
        for i in range(r, m):
            ops += 1
            if rows[i] & bit:
                pivot = i
                break
        if pivot < 0:
            continue
        rows[r], rows[pivot] = rows[pivot], rows[r]
        history[r], history[pivot] = history[pivot], history[r]
        pr, ph = rows[r], history[r]
        for i in range(m):
            if i != r and rows[i] & bit:
                rows[i] ^= pr
                history[i] ^= ph
                ops += 1
                row_xors += 1
        pivots.append(col + 1)
        r += 1
        if r == m:
            break

    rank = r
    for i in range(rank, m):
        ops += 1
        if rows[i] & coeff_mask == 0 and rows[i] >> n & 1:
            cert = [j for j in range(m) if history[i] >> j & 1]
            return {
                "sat": False,
                "assignment": None,
                "certificate": cert,
                "rank": rank,
                "pivots": pivots,
                "ops": ops,
                "row_xors": row_xors,
            }

    assignment = [False] * n
    for i, var in enumerate(pivots):
        ops += 1
        assignment[var - 1] = bool(rows[i] >> n & 1)

    return {
        "sat": True,
        "assignment": assignment,
        "certificate": None,
        "rank": rank,
        "pivots": pivots,
        "ops": ops,
        "row_xors": row_xors,
    }


def verifies(n: int, equations: list[Equation], assignment: list[bool]) -> bool:
    """True when the assignment satisfies every equation."""
    if len(assignment) != n:
        return False
    x = 0
    for i, value in enumerate(assignment):
        if value:
            x |= 1 << i
    coeff_mask = (1 << n) - 1
    for vs, b in equations:
        row = pack(n, vs, b)
        if _popcount(row & coeff_mask & x) & 1 != row >> n & 1:
            return False
    return True


def verify_certificate(n: int, equations: list[Equation], certificate: list[int]) -> bool:
    """True when the named equations XOR to 0 = 1, which proves the system UNSAT.

    Any assignment satisfying every equation would satisfy their XOR, and no
    assignment satisfies 0 = 1. The check is one linear pass.
    """
    if not certificate or len(set(certificate)) != len(certificate):
        return False
    acc = 0
    for j in certificate:
        if not 0 <= j < len(equations):
            return False
        vs, b = equations[j]
        acc ^= pack(n, vs, b)
    return acc == 1 << n
