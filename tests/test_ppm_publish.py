"""
Tests for the ``ppm publish`` command — verify metadata reading, wheel
discovery, multipart encoding, and the HTTP upload flow.
"""
import hashlib
import json
import os
import sys
import textwrap
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

import pytest

# Ensure repo root is importable
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from ppm_cli import (  # noqa: E402
    _read_toml_field,
    _sha256_file,
    _discover_wheels,
    _multipart_encode,
    cmd_publish,
    build_parser,
    main as ppm_main,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_toml(tmp_path, name="my-pkg", version="1.2.3", registry=None):
    """Write a minimal PPM.toml and return its path."""
    reg_line = f'registry = "{registry}"' if registry else ""
    content = textwrap.dedent(f"""\
        [project]
        name = "{name}"
        version = "{version}"

        [tool.ppm]
        {reg_line}
    """)
    toml_path = tmp_path / "PPM.toml"
    toml_path.write_text(content)
    return str(toml_path)


def _make_wheel(tmp_path, filename="my_pkg-1.2.3-py3-none-any.whl"):
    """Create a fake wheel file with deterministic content."""
    wh_dir = tmp_path / "wheelhouse"
    wh_dir.mkdir(exist_ok=True)
    whl = wh_dir / filename
    whl.write_bytes(b"PK\x03\x04fake-wheel-content")
    return str(wh_dir), str(whl)


# ---------------------------------------------------------------------------
# Unit tests — helper functions
# ---------------------------------------------------------------------------

class TestReadTomlField:
    def test_reads_project_name(self, tmp_path):
        _make_toml(tmp_path, name="hello")
        assert _read_toml_field(str(tmp_path / "PPM.toml"), "project", "name") == "hello"

    def test_reads_project_version(self, tmp_path):
        _make_toml(tmp_path, version="9.8.7")
        assert _read_toml_field(str(tmp_path / "PPM.toml"), "project", "version") == "9.8.7"

    def test_reads_registry(self, tmp_path):
        _make_toml(tmp_path, registry="https://r.example.com")
        val = _read_toml_field(str(tmp_path / "PPM.toml"), "tool.ppm", "registry")
        assert val == "https://r.example.com"

    def test_missing_file(self):
        assert _read_toml_field("/nonexistent/PPM.toml", "project", "name") is None

    def test_missing_key(self, tmp_path):
        _make_toml(tmp_path)
        assert _read_toml_field(str(tmp_path / "PPM.toml"), "project", "missing") is None


class TestSha256File:
    def test_hash_matches(self, tmp_path):
        f = tmp_path / "data.bin"
        f.write_bytes(b"hello world")
        expected = hashlib.sha256(b"hello world").hexdigest()
        assert _sha256_file(str(f)) == expected


class TestDiscoverWheels:
    def test_finds_wheels(self, tmp_path):
        wh = tmp_path / "wh"
        wh.mkdir()
        (wh / "a-1.0-py3-none-any.whl").write_bytes(b"A")
        (wh / "b-2.0-py3-none-any.whl").write_bytes(b"B")
        (wh / "not-a-wheel.tar.gz").write_bytes(b"C")
        result = _discover_wheels(str(wh))
        assert len(result) == 2
        assert all(r.endswith(".whl") for r in result)

    def test_empty_dir(self, tmp_path):
        wh = tmp_path / "empty"
        wh.mkdir()
        assert _discover_wheels(str(wh)) == []

    def test_missing_dir(self):
        assert _discover_wheels("/nonexistent") == []


class TestMultipartEncode:
    def test_contains_fields(self):
        body, ct = _multipart_encode(
            {"name": "pkg", "version": "1.0"},
            {"file": ("test.whl", b"data")},
        )
        assert b"name" in body
        assert b"pkg" in body
        assert b"test.whl" in body
        assert b"data" in body
        assert "multipart/form-data" in ct

    def test_boundary_in_content_type(self):
        _, ct = _multipart_encode({}, {})
        assert "boundary=" in ct


# ---------------------------------------------------------------------------
# Integration test — publish with a local HTTP server
# ---------------------------------------------------------------------------

class _UploadHandler(BaseHTTPRequestHandler):
    """Captures the last POST and returns 200."""
    uploads = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        auth = self.headers.get("Authorization", "")
        ct = self.headers.get("Content-Type", "")
        self.server.last_upload = {
            "path": self.path,
            "auth": auth,
            "content_type": ct,
            "body_len": len(body),
            "body_preview": body[:500],
        }
        _UploadHandler.uploads.append(self.server.last_upload)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def log_message(self, *_a):
        pass  # suppress request logs


class TestPublishIntegration:
    @pytest.fixture(autouse=True)
    def setup_server(self):
        _UploadHandler.uploads = []
        self.server = HTTPServer(("127.0.0.1", 0), _UploadHandler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.daemon = True
        self.thread.start()
        yield
        self.server.shutdown()

    def test_publish_uploads_wheel(self, tmp_path, capsys):
        _make_toml(tmp_path, name="test-pkg", version="0.1.0")
        wh_dir, _ = _make_wheel(tmp_path)

        registry_url = f"http://127.0.0.1:{self.port}"
        ppm_main([
            "--root", str(tmp_path),
            "publish",
            "--registry", registry_url,
            "--token", "test-token-123",
            "--wheelhouse", wh_dir,
        ])

        assert len(_UploadHandler.uploads) == 1
        upload = _UploadHandler.uploads[0]
        assert upload["path"] == "/api/v1/upload"
        assert upload["auth"] == "Bearer test-token-123"
        assert b"test-pkg" in upload["body_preview"]

        captured = capsys.readouterr()
        assert "1/1 wheel(s)" in captured.out

    def test_publish_no_registry_fails(self, tmp_path):
        _make_toml(tmp_path)
        wh_dir, _ = _make_wheel(tmp_path)
        # Clear env vars
        env_backup = {}
        for k in ("PPM_REGISTRY_URL", "PPM_REGISTRY_TOKEN"):
            env_backup[k] = os.environ.pop(k, None)
        try:
            with pytest.raises(SystemExit):
                ppm_main([
                    "--root", str(tmp_path),
                    "publish",
                    "--wheelhouse", wh_dir,
                ])
        finally:
            for k, v in env_backup.items():
                if v is not None:
                    os.environ[k] = v

    def test_publish_no_token_fails(self, tmp_path):
        _make_toml(tmp_path, registry="https://example.com")
        wh_dir, _ = _make_wheel(tmp_path)
        env_backup = os.environ.pop("PPM_REGISTRY_TOKEN", None)
        try:
            with pytest.raises(SystemExit):
                ppm_main([
                    "--root", str(tmp_path),
                    "publish",
                    "--registry", "https://example.com",
                    "--wheelhouse", wh_dir,
                ])
        finally:
            if env_backup is not None:
                os.environ["PPM_REGISTRY_TOKEN"] = env_backup

    def test_publish_no_wheels_exits_clean(self, tmp_path, capsys):
        _make_toml(tmp_path)
        empty_wh = tmp_path / "empty_wh"
        empty_wh.mkdir()

        with pytest.raises(SystemExit) as exc_info:
            ppm_main([
                "--root", str(tmp_path),
                "publish",
                "--registry", "https://example.com",
                "--token", "tok",
                "--wheelhouse", str(empty_wh),
            ])
        # exit(0) — not an error
        assert exc_info.value.code == 0

    def test_publish_multiple_wheels(self, tmp_path, capsys):
        _make_toml(tmp_path, name="multi", version="2.0.0")
        wh_dir = str(tmp_path / "wheelhouse")
        os.makedirs(wh_dir, exist_ok=True)
        for i in range(3):
            with open(os.path.join(wh_dir, f"multi-2.0.0-cp3{i}-linux.whl"), "wb") as f:
                f.write(f"wheel-{i}".encode())

        registry_url = f"http://127.0.0.1:{self.port}"
        ppm_main([
            "--root", str(tmp_path),
            "publish",
            "--registry", registry_url,
            "--token", "tok",
            "--wheelhouse", wh_dir,
        ])

        assert len(_UploadHandler.uploads) == 3
        captured = capsys.readouterr()
        assert "3/3 wheel(s)" in captured.out
