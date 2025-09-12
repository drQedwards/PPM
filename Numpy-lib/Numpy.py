 Pure-Python (NumPy) fallback for environments where the Cython extension isn't built.
# This mirrors the public API of numpy-lib (vector_add, dot, scale_inplace).

from typing import Iterable
import numpy as np

def _as_f64_1d(x) -> np.ndarray:
    a = np.asarray(x, dtype=np.float64)
    if a.ndim != 1:
        raise ValueError("Expected a 1D array-like")
    return a

def vector_add(a: Iterable[float], b: Iterable[float]) -> np.ndarray:
    a = _as_f64_1d(a)
    b = _as_f64_1d(b)
    if a.shape[0] != b.shape[0]:
        raise ValueError("Length mismatch")
    return a + b

def dot(a: Iterable[float], b: Iterable[float]) -> float:
    a = _as_f64_1d(a)
    b = _as_f64_1d(b)
    if a.shape[0] != b.shape[0]:
        raise ValueError("Length mismatch")
    return float(np.dot(a, b))

def scale_inplace(a: np.ndarray, alpha: float) -> None:
    arr = _as_f64_1d(a)
    arr *= float(alpha)
