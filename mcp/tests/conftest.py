"""Give every test its own SQLite graph database.

The memory graph persists to SQLite (default: ~/.local/share/pmll/). Without
this fixture, tests that reuse a session_id see rows left by earlier tests or
earlier runs, and their counts drift."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pmll_memory_mcp.memory_graph import _graph_stores, configure_db  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_graph_db(tmp_path):
    configure_db(str(tmp_path / "isolated_graph.sqlite3"))
    yield
    _graph_stores.clear()
