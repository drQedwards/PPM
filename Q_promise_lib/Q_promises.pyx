# cython: language_level=3
"""Deprecated Cython bridge (QMemNode seed removed).

Build the C library with ``make shared`` and use ``qpromise.h`` / ctypes.
This file remains so setup.py does not break tree layout checks; it exposes
no runtime API.
"""

def deprecated_notice():
    return "Use qpromise C API (qpromise.h); QMemNode seed removed."
