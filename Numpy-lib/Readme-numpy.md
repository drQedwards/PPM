# PPM numpy-lib mini

This provides a tiny NumPy-backed extension with both a C/Cython path and a pure-Python fallback.

## Files

- `numpy-lib.h` — C header with function declarations.
- `numpy-lib.c` — C implementation (no external deps).
- `numpy-lib.pyx` — Cython wrapper exposing `vector_add`, `dot`, `scale_inplace`.
- `numpy-lib.py` — Pure Python fallback mirroring the same API.

## Build (standard setuptools + Cython)

Example `pyproject.toml` (if you need one):

[build-system]
requires = ["setuptools>=64", "wheel", "cython", "numpy"]
build-backend = "setuptools.build_meta"

Example `setup.py`:

from setuptools import setup, Extension
from Cython.Build import cythonize
import numpy as np

exts = [
    Extension(
        name="numpy_lib",
        sources=["numpy-lib.pyx", "numpy-lib.c"],
        include_dirs=[np.get_include()],
        language="c",
    )
]

setup(
    name="numpy-lib",
    version="0.1.0",
    ext_modules=cythonize(exts, compiler_directives={"language_level": "3"}),
    py_modules=["numpy-lib"],  # keep the pure-Python fallback importable
)

Then build & install:

pip install .
# or
python -m build && pip install dist/*.whl

## Usage

import numpy as np
try:
    import numpy_lib as nlib   # compiled extension
except ImportError:
    import numpy_lib as nlib   # fallback (ensure the filename is numpy_lib.py if you want underscore import)

a = np.arange(5, dtype=np.float64)
b = np.ones(5, dtype=np.float64)
print(nlib.vector_add(a, b))
print(nlib.dot(a, b))
nlib.scale_inplace(a, 2.0)
print(a)
