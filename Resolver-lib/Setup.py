from setuptools import setup, Extension
from Cython.Build import cythonize
import os

USE_CUDA = os.environ.get("USE_CUDA", "0") == "1"

extra_objects = []
libraries = []
library_dirs = []
extra_compile_args = []
extra_link_args = []

# If you've built libmatrix.a from matrix.cu:
#   nvcc -O3 -std=c++17 -Xcompiler -fPIC -c matrix.cu -o matrix.o
#   ar rcs libmatrix.a matrix.o
if USE_CUDA:
    libraries += []
    extra_objects += ["libmatrix.a"]  # path relative to this setup.py
    extra_link_args += ["-lcudart"]
    # If CUDA is in a nonstandard path, set CUDA_HOME and add:
    cuda_home = os.environ.get("CUDA_HOME", "/usr/local/cuda")
    library_dirs += [os.path.join(cuda_home, "lib64")]

ext = Extension(
    name="importresolver",
    sources=["importresolver.pyx"],
    include_dirs=["."],
    libraries=libraries,
    library_dirs=library_dirs,
    extra_objects=extra_objects,
    extra_compile_args=extra_compile_args,
    extra_link_args=extra_link_args,
)

setup(
    name="importresolver",
    version="0.1.0",
    ext_modules=cythonize([ext], language_level=3),
)
