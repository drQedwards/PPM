"""Optional packaging stub. Core library builds with Make, not setuptools."""
from setuptools import setup

setup(
    name="Q_promises",
    version="1.0.0",
    description="PMLL Promise/Continuation Library (C core via Make)",
    py_modules=["Q_promises"],
)
