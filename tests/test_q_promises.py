"""
Tests for the PMLL Promise / Continuation Library (Q_promise_lib).

Primary coverage is the deterministic C suite (test_qpromise). These Python
tests verify the package layout and that ``make test`` / the shared library
build succeed. The QMemNode seed API is intentionally gone.
"""
import os
import subprocess

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
Q_LIB_DIR = os.path.join(REPO_ROOT, "Q_promise_lib")


@pytest.fixture(scope="session", autouse=True)
def build_and_run_c_suite():
    subprocess.check_call(["make", "clean"], cwd=Q_LIB_DIR)
    subprocess.check_call(["make", "test"], cwd=Q_LIB_DIR)
    subprocess.check_call(["make", "shared"], cwd=Q_LIB_DIR)


class TestQPromiseLibLayout:
    def test_directory_exists(self):
        assert os.path.isdir(Q_LIB_DIR)

    def test_header_present(self):
        assert os.path.isfile(os.path.join(Q_LIB_DIR, "qpromise.h"))
        assert os.path.isfile(os.path.join(Q_LIB_DIR, "Q_promises.h"))

    def test_sources_present(self):
        assert os.path.isfile(os.path.join(Q_LIB_DIR, "qpromise.c"))
        assert os.path.isfile(os.path.join(Q_LIB_DIR, "test_qpromise.c"))
        assert os.path.isfile(os.path.join(Q_LIB_DIR, "README.md"))

    def test_shared_library_builds(self):
        assert os.path.isfile(os.path.join(Q_LIB_DIR, "libqpromise.so"))

    def test_c_suite_binary_exists(self):
        assert os.path.isfile(os.path.join(Q_LIB_DIR, "test_qpromise"))


class TestQPromiseCAPI:
    def test_rerun_c_suite(self):
        result = subprocess.run(
            [os.path.join(Q_LIB_DIR, "test_qpromise")],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr + result.stdout
        assert "failures" in result.stdout
        assert ", 0 failures" in result.stdout
