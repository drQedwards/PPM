"""
Tests for the Q_promise_lib — a lightweight thenable memory-chain simulator
inspired by Kris Kowal's Q promises, integrated as a PPM plugin.

These tests validate:
  1. The C shared library (via ctypes) builds and exposes the expected API.
  2. The memory chain allocates correctly and returns valid data.
  3. The q_then callback mechanism invokes for every node.
  4. Edge cases (zero-length chain, large chain) are handled safely.
"""
import ctypes
import os
import subprocess
import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
Q_LIB_DIR = os.path.join(REPO_ROOT, "Q_promise_lib")
SO_PATH = os.path.join(Q_LIB_DIR, "q_promises.so")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session", autouse=True)
def build_shared_library():
    """Compile Q_promises.c into a shared library before tests run."""
    subprocess.check_call(
        ["make", "clean"],
        cwd=Q_LIB_DIR,
    )
    subprocess.check_call(
        ["make", os.path.basename(SO_PATH)],
        cwd=Q_LIB_DIR,
    )
    assert os.path.exists(SO_PATH), f"Shared library not found at {SO_PATH}"


@pytest.fixture(scope="session")
def qlib(build_shared_library):
    """Load the Q_promises shared library via ctypes."""
    lib = ctypes.CDLL(SO_PATH)

    # q_mem_create_chain(size_t) -> QMemNode*
    lib.q_mem_create_chain.argtypes = [ctypes.c_size_t]
    lib.q_mem_create_chain.restype = ctypes.c_void_p

    # q_mem_free_chain(QMemNode*) -> void
    lib.q_mem_free_chain.argtypes = [ctypes.c_void_p]
    lib.q_mem_free_chain.restype = None

    # q_then(QMemNode*, callback) -> void
    CALLBACK_TYPE = ctypes.CFUNCTYPE(None, ctypes.c_long, ctypes.c_char_p)
    lib._CALLBACK_TYPE = CALLBACK_TYPE
    lib.q_then.argtypes = [ctypes.c_void_p, CALLBACK_TYPE]
    lib.q_then.restype = None

    return lib


# ---------------------------------------------------------------------------
# Tests — C shared library via ctypes
# ---------------------------------------------------------------------------
class TestQPromisesSharedLibrary:
    """Test the Q_promises C API through the compiled shared library."""

    def test_library_loads(self, qlib):
        """The shared library loads successfully."""
        assert qlib is not None

    def test_create_chain_returns_non_null(self, qlib):
        """q_mem_create_chain returns a valid pointer for length > 0."""
        head = qlib.q_mem_create_chain(5)
        assert head is not None and head != 0
        qlib.q_mem_free_chain(head)

    def test_create_chain_zero_returns_null(self, qlib):
        """q_mem_create_chain(0) returns NULL."""
        head = qlib.q_mem_create_chain(0)
        assert head is None or head == 0

    def test_q_then_invokes_callback(self, qlib):
        """q_then invokes the callback for every node in the chain."""
        chain_len = 6
        results = []

        @qlib._CALLBACK_TYPE
        def cb(index, payload):
            results.append((index, payload.decode("utf-8") if payload else None))

        head = qlib.q_mem_create_chain(chain_len)
        qlib.q_then(head, cb)
        qlib.q_mem_free_chain(head)

        assert len(results) == chain_len

    def test_q_then_payload_pattern(self, qlib):
        """Even-indexed nodes carry 'Known', odd-indexed carry 'Unknown'."""
        chain_len = 8
        results = []

        @qlib._CALLBACK_TYPE
        def cb(index, payload):
            results.append((index, payload.decode("utf-8") if payload else None))

        head = qlib.q_mem_create_chain(chain_len)
        qlib.q_then(head, cb)
        qlib.q_mem_free_chain(head)

        for idx, payload in results:
            if idx % 2 == 0:
                assert payload == "Known", f"Node {idx} should be 'Known'"
            else:
                assert payload == "Unknown", f"Node {idx} should be 'Unknown'"

    def test_q_then_indices_sequential(self, qlib):
        """Callback indices are sequential starting from 0."""
        chain_len = 10
        indices = []

        @qlib._CALLBACK_TYPE
        def cb(index, payload):
            indices.append(index)

        head = qlib.q_mem_create_chain(chain_len)
        qlib.q_then(head, cb)
        qlib.q_mem_free_chain(head)

        assert indices == list(range(chain_len))

    def test_large_chain(self, qlib):
        """A large chain (1000 nodes) allocates and iterates without error."""
        chain_len = 1000
        count = [0]

        @qlib._CALLBACK_TYPE
        def cb(index, payload):
            count[0] += 1

        head = qlib.q_mem_create_chain(chain_len)
        assert head is not None and head != 0
        qlib.q_then(head, cb)
        qlib.q_mem_free_chain(head)

        assert count[0] == chain_len

    def test_free_chain_does_not_crash(self, qlib):
        """Calling q_mem_free_chain on a valid chain completes without error."""
        head = qlib.q_mem_create_chain(3)
        qlib.q_mem_free_chain(head)
        # If we get here without a segfault, the test passes.

    def test_free_null_chain(self, qlib):
        """Calling q_mem_free_chain(NULL) does not crash."""
        qlib.q_mem_free_chain(None)


# ---------------------------------------------------------------------------
# Tests — Standalone C executable (Promises.c)
# ---------------------------------------------------------------------------
class TestPromisesExecutable:
    """Test the standalone Promises.c executable."""

    @pytest.fixture(scope="class", autouse=True)
    def build_executable(self):
        """Compile Promises.c into a standalone test binary."""
        subprocess.check_call(
            ["make", "test_promises"],
            cwd=Q_LIB_DIR,
        )

    def test_executable_runs(self):
        """The compiled Promises.c binary runs and exits cleanly."""
        result = subprocess.run(
            [os.path.join(Q_LIB_DIR, "test_promises")],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_executable_output_header(self):
        """Output starts with the expected header line."""
        result = subprocess.run(
            [os.path.join(Q_LIB_DIR, "test_promises")],
            capture_output=True,
            text=True,
        )
        lines = result.stdout.strip().split("\n")
        assert lines[0] == "Beginning memory trace:"

    def test_executable_output_count(self):
        """The binary prints exactly 10 resolved memory lines + 1 header."""
        result = subprocess.run(
            [os.path.join(Q_LIB_DIR, "test_promises")],
            capture_output=True,
            text=True,
        )
        lines = result.stdout.strip().split("\n")
        # 1 header + 10 memory lines = 11
        assert len(lines) == 11

    def test_executable_output_pattern(self):
        """Each memory line follows 'Resolved Memory[N] → Known/Unknown'."""
        result = subprocess.run(
            [os.path.join(Q_LIB_DIR, "test_promises")],
            capture_output=True,
            text=True,
        )
        lines = result.stdout.strip().split("\n")[1:]  # skip header
        for i, line in enumerate(lines):
            expected_data = "Known" if i % 2 == 0 else "Unknown"
            assert f"Memory[{i}]" in line
            assert expected_data in line


# ---------------------------------------------------------------------------
# Tests — PPM integration (package registration)
# ---------------------------------------------------------------------------
class TestPPMIntegration:
    """Verify Q_promise_lib is properly structured as a PPM-compatible package."""

    def test_q_promise_lib_directory_exists(self):
        """Q_promise_lib directory exists in the repository root."""
        assert os.path.isdir(Q_LIB_DIR)

    def test_header_file_present(self):
        """Q_promises.h header is present."""
        assert os.path.isfile(os.path.join(Q_LIB_DIR, "Q_promises.h"))

    def test_c_source_present(self):
        """Q_promises.c source is present."""
        assert os.path.isfile(os.path.join(Q_LIB_DIR, "Q_promises.c"))

    def test_cython_bridge_present(self):
        """Q_promises.pyx Cython bridge is present."""
        assert os.path.isfile(os.path.join(Q_LIB_DIR, "Q_promises.pyx"))

    def test_python_wrapper_present(self):
        """Q_promises.py high-level wrapper is present."""
        assert os.path.isfile(os.path.join(Q_LIB_DIR, "Q_promises.py"))

    def test_setup_py_present(self):
        """Setup.py build config is present."""
        assert os.path.isfile(os.path.join(Q_LIB_DIR, "Setup.py"))

    def test_makefile_present(self):
        """Makefile for C builds is present."""
        assert os.path.isfile(os.path.join(Q_LIB_DIR, "Makefile"))

    def test_shared_library_builds(self):
        """The shared library builds via make."""
        assert os.path.isfile(SO_PATH)
