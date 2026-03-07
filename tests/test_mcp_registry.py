"""
Tests for MCP Registry metadata validation — ``ppm validate-mcp`` command
and the supporting ``_read_json_field`` / ``_validate_mcp_name`` helpers.
"""
import json
import os
import sys

import pytest

# Ensure repo root is importable
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from ppm_cli import (  # noqa: E402
    _read_json_field,
    _validate_mcp_name,
    cmd_validate_mcp,
    build_parser,
    main as ppm_main,
)


# ---------------------------------------------------------------------------
# Unit tests — _read_json_field
# ---------------------------------------------------------------------------

class TestReadJsonField:
    def test_reads_top_level_key(self, tmp_path):
        pkg = tmp_path / "package.json"
        pkg.write_text(json.dumps({"mcpName": "io.github.user/server"}))
        assert _read_json_field(str(pkg), "mcpName") == "io.github.user/server"

    def test_reads_nested_key(self, tmp_path):
        pkg = tmp_path / "package.json"
        pkg.write_text(json.dumps({"repository": {"type": "git", "url": "https://example.com"}}))
        assert _read_json_field(str(pkg), "repository", "url") == "https://example.com"

    def test_missing_file(self):
        assert _read_json_field("/nonexistent/package.json", "mcpName") is None

    def test_missing_key(self, tmp_path):
        pkg = tmp_path / "package.json"
        pkg.write_text(json.dumps({"name": "test"}))
        assert _read_json_field(str(pkg), "mcpName") is None

    def test_invalid_json(self, tmp_path):
        pkg = tmp_path / "package.json"
        pkg.write_text("not json {{{")
        assert _read_json_field(str(pkg), "mcpName") is None

    def test_nested_missing_intermediate(self, tmp_path):
        pkg = tmp_path / "package.json"
        pkg.write_text(json.dumps({"name": "test"}))
        assert _read_json_field(str(pkg), "repository", "url") is None


# ---------------------------------------------------------------------------
# Unit tests — _validate_mcp_name
# ---------------------------------------------------------------------------

class TestValidateMcpName:
    def test_valid_github_name(self):
        assert _validate_mcp_name("io.github.user/server") == []

    def test_empty_name(self):
        errors = _validate_mcp_name("")
        assert len(errors) == 1
        assert "empty or missing" in errors[0]

    def test_none_name(self):
        errors = _validate_mcp_name(None)
        assert len(errors) == 1
        assert "empty or missing" in errors[0]

    def test_no_slash(self):
        errors = _validate_mcp_name("io.github.user")
        assert len(errors) == 1
        assert "/" in errors[0]

    def test_non_github_prefix(self):
        errors = _validate_mcp_name("com.example/server")
        assert len(errors) == 1
        assert "io.github" in errors[0]


# ---------------------------------------------------------------------------
# Integration tests — validate-mcp command
# ---------------------------------------------------------------------------

class TestValidateMcpCommand:
    def _write_package_json(self, root, data):
        pkg = root / "package.json"
        pkg.write_text(json.dumps(data, indent=2))

    def _write_manifest(self, root, data):
        mcp_dir = root / "mcp"
        mcp_dir.mkdir(exist_ok=True)
        manifest = mcp_dir / "mcp_manifest.json"
        manifest.write_text(json.dumps(data, indent=2))

    def test_valid_metadata(self, tmp_path, capsys):
        self._write_package_json(tmp_path, {
            "name": "test-pkg",
            "mcpName": "io.github.testuser/test-server",
            "description": "A test server",
            "repository": {"type": "git", "url": "https://github.com/testuser/test.git"},
        })
        self._write_manifest(tmp_path, {
            "name": "test-server",
            "mcpName": "io.github.testuser/test-server",
        })

        ppm_main(["--root", str(tmp_path), "validate-mcp"])
        captured = capsys.readouterr()
        assert "MCP Registry metadata is valid" in captured.out

    def test_missing_mcp_name_fails(self, tmp_path, capsys):
        self._write_package_json(tmp_path, {
            "name": "test-pkg",
            "description": "A test server",
        })

        ppm_main(["--root", str(tmp_path), "validate-mcp"])
        captured = capsys.readouterr()
        assert "missing 'mcpName'" in captured.out

    def test_fail_on_error_exits(self, tmp_path):
        self._write_package_json(tmp_path, {
            "name": "test-pkg",
        })

        with pytest.raises(SystemExit) as exc_info:
            ppm_main([
                "--root", str(tmp_path),
                "validate-mcp",
                "--fail-on-error",
            ])
        assert exc_info.value.code == 1

    def test_mismatch_detected(self, tmp_path, capsys):
        self._write_package_json(tmp_path, {
            "name": "test-pkg",
            "mcpName": "io.github.user/server-a",
            "description": "A test",
            "repository": {"type": "git", "url": "https://example.com"},
        })
        self._write_manifest(tmp_path, {
            "name": "test-server",
            "mcpName": "io.github.user/server-b",
        })

        ppm_main(["--root", str(tmp_path), "validate-mcp"])
        captured = capsys.readouterr()
        assert "mismatch" in captured.out

    def test_no_package_json(self, tmp_path, capsys):
        ppm_main(["--root", str(tmp_path), "validate-mcp"])
        captured = capsys.readouterr()
        assert "not found" in captured.out


# ---------------------------------------------------------------------------
# Verify real project files
# ---------------------------------------------------------------------------

class TestRealProjectMcpMetadata:
    """Ensure the actual project package.json has valid MCP metadata."""

    def test_package_json_has_mcp_name(self):
        pkg_path = os.path.join(REPO_ROOT, "package.json")
        mcp_name = _read_json_field(pkg_path, "mcpName")
        assert mcp_name is not None, "package.json must have 'mcpName'"
        assert mcp_name.startswith("io.github."), \
            f"mcpName should start with 'io.github.' for GitHub auth, got: {mcp_name}"

    def test_package_json_has_description(self):
        pkg_path = os.path.join(REPO_ROOT, "package.json")
        desc = _read_json_field(pkg_path, "description")
        assert desc, "package.json 'description' should not be empty"

    def test_package_json_has_repository(self):
        pkg_path = os.path.join(REPO_ROOT, "package.json")
        repo_url = _read_json_field(pkg_path, "repository", "url")
        assert repo_url is not None, "package.json must have 'repository.url'"
        assert "drQedwards/PPM" in repo_url, \
            f"repository.url should reference drQedwards/PPM, got: {repo_url}"

    def test_mcp_manifest_has_mcp_name(self):
        manifest_path = os.path.join(REPO_ROOT, "mcp", "mcp_manifest.json")
        mcp_name = _read_json_field(manifest_path, "mcpName")
        assert mcp_name is not None, "mcp_manifest.json must have 'mcpName'"

    def test_mcp_names_match(self):
        pkg_path = os.path.join(REPO_ROOT, "package.json")
        manifest_path = os.path.join(REPO_ROOT, "mcp", "mcp_manifest.json")
        pkg_name = _read_json_field(pkg_path, "mcpName")
        manifest_name = _read_json_field(manifest_path, "mcpName")
        assert pkg_name == manifest_name, \
            f"mcpName mismatch: package.json={pkg_name}, manifest={manifest_name}"
