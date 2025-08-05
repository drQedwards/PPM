"""High-level Python wrapper for the Q_promises Cython module."""
from typing import Callable, Optional

try:
    import Q_promises  # Pyx-compiled module
except ImportError as e:
    raise RuntimeError(
        "Q_promises extension not compiled. "
        "Run `pip install -e .` in the Q_promise_lib directory first."
    ) from e


def trace(size: int, callback: Optional[Callable[[int, str], None]] = None) -> None:
    """Convenience wrapper around the Cython trace() function."""
    Q_promises.trace(size, callback)
