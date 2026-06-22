"""Tiny pure-Python linear algebra for the DIEP DMS analytics engines (P5).

The FastAPI runtime image deliberately ships NO numpy/scipy (see
fastapi/requirements.txt) — keeping the production image small and its builds
reproducible. The P5 state estimator (M2) and power flow (M3) operate on small
distribution feeders (tens of nodes), so dense O(n^3) Gaussian elimination is
more than fast enough and adds zero runtime dependencies.

Everything here is plain lists of floats (`list[list[float]]` matrices,
`list[float]` vectors). No mutation of inputs.
"""
from __future__ import annotations


def zeros(rows: int, cols: int) -> list[list[float]]:
    return [[0.0] * cols for _ in range(rows)]


def identity(n: int) -> list[list[float]]:
    m = zeros(n, n)
    for i in range(n):
        m[i][i] = 1.0
    return m


def transpose(a: list[list[float]]) -> list[list[float]]:
    return [list(col) for col in zip(*a)] if a else []


def matmul(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    bt = transpose(b)
    return [[sum(ai * bj for ai, bj in zip(row, col)) for col in bt] for row in a]


def matvec(a: list[list[float]], x: list[float]) -> list[float]:
    return [sum(ai * xi for ai, xi in zip(row, x)) for row in a]


def solve(a: list[list[float]], b: list[float]) -> list[float]:
    """Solve A x = b for square A via Gaussian elimination with partial pivoting.
    Raises ValueError if A is singular."""
    n = len(a)
    # augmented copy
    m = [list(a[i]) + [b[i]] for i in range(n)]
    for col in range(n):
        # pivot
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-12:
            raise ValueError("singular matrix in solve()")
        m[col], m[piv] = m[piv], m[col]
        pv = m[col][col]
        for r in range(n):
            if r == col:
                continue
            factor = m[r][col] / pv
            if factor != 0.0:
                for c in range(col, n + 1):
                    m[r][c] -= factor * m[col][c]
    return [m[i][n] / m[i][i] for i in range(n)]


def inverse(a: list[list[float]]) -> list[list[float]]:
    """Inverse of square A via Gauss-Jordan with partial pivoting."""
    n = len(a)
    m = [list(a[i]) + identity(n)[i] for i in range(n)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-12:
            raise ValueError("singular matrix in inverse()")
        m[col], m[piv] = m[piv], m[col]
        pv = m[col][col]
        m[col] = [v / pv for v in m[col]]
        for r in range(n):
            if r == col:
                continue
            factor = m[r][col]
            if factor != 0.0:
                m[r] = [vr - factor * vc for vr, vc in zip(m[r], m[col])]
    return [row[n:] for row in m]
