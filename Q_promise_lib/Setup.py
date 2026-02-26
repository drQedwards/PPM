from setuptools import setup, Extension
from Cython.Build import cythonize

ext = Extension(
    name="Q_promises",
    sources=["Q_promises.pyx", "Q_promises.c"],
    include_dirs=["."],
    language="c",
)

setup(
    name="Q_promises",
    version="0.1.0",
    description="Lightweight thenable memory-chain simulator inspired by Q promises",
    ext_modules=cythonize([ext], language_level=3),
)
