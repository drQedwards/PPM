from setuptools import setup, Extension
from Cython.Build import cythonize
import sysconfig

py_inc = sysconfig.get_paths()["include"]

ext = Extension(
    "pandas_bridge",
    sources=["pandas_bridge.pyx"],
    include_dirs=[py_inc],
    language="c",
)

setup(
    name="pandas_bridge",
    ext_modules=cythonize([ext], compiler_directives={"language_level": "3"}),
)
