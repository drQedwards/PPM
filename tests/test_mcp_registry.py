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
    cmd_init_mcp,
    cmd_publish_mcp,
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

    def test_server_json_exists(self):
        server_path = os.path.join(REPO_ROOT, "server.json")
        assert os.path.exists(server_path), "server.json must exist for MCP Registry publishing"

    def test_server_json_name_matches_package(self):
        pkg_path = os.path.join(REPO_ROOT, "package.json")
        server_path = os.path.join(REPO_ROOT, "server.json")
        pkg_name = _read_json_field(pkg_path, "mcpName")
        server_name = _read_json_field(server_path, "name")
        assert server_name == pkg_name, \
            f"server.json name mismatch: package.json={pkg_name}, server.json={server_name}"


# ---------------------------------------------------------------------------
# Integration tests — validate-mcp with server.json
# ---------------------------------------------------------------------------

class TestValidateMcpServerJson:
    def _write_package_json(self, root, data):
        pkg = root / "package.json"
        pkg.write_text(json.dumps(data, indent=2))

    def _write_server_json(self, root, data):
        path = root / "server.json"
        path.write_text(json.dumps(data, indent=2))

    def test_server_json_name_shown(self, tmp_path, capsys):
        self._write_package_json(tmp_path, {
            "name": "test-pkg",
            "mcpName": "io.github.user/server",
            "description": "A test server",
            "repository": {"type": "git", "url": "https://example.com"},
        })
        self._write_server_json(tmp_path, {
            "name": "io.github.user/server",
        })

        ppm_main(["--root", str(tmp_path), "validate-mcp"])
        captured = capsys.readouterr()
        assert "server.json name: io.github.user/server" in captured.out

    def test_server_json_name_mismatch(self, tmp_path, capsys):
        self._write_package_json(tmp_path, {
            "name": "test-pkg",
            "mcpName": "io.github.user/server-a",
            "description": "A test",
            "repository": {"type": "git", "url": "https://example.com"},
        })
        self._write_server_json(tmp_path, {
            "name": "io.github.user/server-b",
        })

        ppm_main(["--root", str(tmp_path), "validate-mcp"])
        captured = capsys.readouterr()
        assert "mismatch" in captured.out

    def test_missing_server_json_info(self, tmp_path, capsys):
        self._write_package_json(tmp_path, {
            "name": "test-pkg",
            "mcpName": "io.github.user/server",
            "description": "A test",
            "repository": {"type": "git", "url": "https://example.com"},
        })

        ppm_main(["--root", str(tmp_path), "validate-mcp"])
        captured = capsys.readouterr()
        assert "server.json not found" in captured.out


# ---------------------------------------------------------------------------
# Integration tests — init-mcp command
# ---------------------------------------------------------------------------

class TestInitMcpCommand:
    def _write_package_json(self, root, data):
        pkg = root / "package.json"
        pkg.write_text(json.dumps(data, indent=2))

    def test_generates_server_json(self, tmp_path, capsys):
        self._write_package_json(tmp_path, {
            "name": "@user/my-server",
            "version": "1.2.3",
            "mcpName": "io.github.user/my-server",
            "description": "Test MCP server",
            "repository": {"type": "git", "url": "git+https://github.com/user/repo.git"},
        })

        ppm_main(["--root", str(tmp_path), "init-mcp"])
        captured = capsys.readouterr()
        assert "Generated" in captured.out

        server_path = tmp_path / "server.json"
        assert server_path.exists()
        with open(server_path) as f:
            server = json.load(f)
        assert server["name"] == "io.github.user/my-server"
        assert server["version"] == "1.2.3"
        assert server["description"] == "Test MCP server"
        assert server["repository"]["url"] == "https://github.com/user/repo"
        assert server["repository"]["source"] == "github"
        assert server["packages"][0]["registryType"] == "npm"
        assert server["packages"][0]["identifier"] == "@user/my-server"

    def test_refuses_overwrite_without_force(self, tmp_path):
        self._write_package_json(tmp_path, {
            "name": "test",
            "mcpName": "io.github.user/test",
        })
        (tmp_path / "server.json").write_text("{}")

        with pytest.raises(SystemExit) as exc_info:
            ppm_main(["--root", str(tmp_path), "init-mcp"])
        assert exc_info.value.code == 1

    def test_force_overwrites(self, tmp_path, capsys):
        self._write_package_json(tmp_path, {
            "name": "test",
            "version": "1.0.0",
            "mcpName": "io.github.user/test",
            "description": "d",
            "repository": {"type": "git", "url": "https://github.com/user/test"},
        })
        (tmp_path / "server.json").write_text("{}")

        ppm_main(["--root", str(tmp_path), "init-mcp", "--force"])
        captured = capsys.readouterr()
        assert "Generated" in captured.out

    def test_fails_without_package_json(self, tmp_path):
        with pytest.raises(SystemExit) as exc_info:
            ppm_main(["--root", str(tmp_path), "init-mcp"])
        assert exc_info.value.code == 1

    def test_fails_without_mcp_name(self, tmp_path):
        self._write_package_json(tmp_path, {"name": "test"})

        with pytest.raises(SystemExit) as exc_info:
            ppm_main(["--root", str(tmp_path), "init-mcp"])
        assert exc_info.value.code == 1

    def test_strips_git_prefix_and_suffix(self, tmp_path):
        self._write_package_json(tmp_path, {
            "name": "test",
            "version": "1.0.0",
            "mcpName": "io.github.user/test",
            "description": "d",
            "repository": {"type": "git", "url": "git+https://github.com/user/repo.git"},
        })

        ppm_main(["--root", str(tmp_path), "init-mcp"])
        with open(tmp_path / "server.json") as f:
            server = json.load(f)
        assert server["repository"]["url"] == "https://github.com/user/repo"


# ---------------------------------------------------------------------------
# Integration tests — publish-mcp command
# ---------------------------------------------------------------------------

class TestPublishMcpCommand:
    def _write_package_json(self, root, data):
        pkg = root / "package.json"
        pkg.write_text(json.dumps(data, indent=2))

    def _write_server_json(self, root, data):
        path = root / "server.json"
        path.write_text(json.dumps(data, indent=2))

    def test_dry_run_succeeds(self, tmp_path, capsys):
        self._write_package_json(tmp_path, {
            "name": "test",
            "mcpName": "io.github.user/test",
        })
        self._write_server_json(tmp_path, {
            "name": "io.github.user/test",
        })

        ppm_main(["--root", str(tmp_path), "publish-mcp", "--dry-run"])
        captured = capsys.readouterr()
        assert "dry-run" in captured.out
        assert "io.github.user/test" in captured.out

    def test_fails_without_mcp_name(self, tmp_path):
        self._write_package_json(tmp_path, {"name": "test"})

        with pytest.raises(SystemExit) as exc_info:
            ppm_main(["--root", str(tmp_path), "publish-mcp", "--dry-run"])
        assert exc_info.value.code == 1

    def test_fails_without_server_json(self, tmp_path):
        self._write_package_json(tmp_path, {
            "name": "test",
            "mcpName": "io.github.user/test",
        })

        with pytest.raises(SystemExit) as exc_info:
            ppm_main(["--root", str(tmp_path), "publish-mcp", "--dry-run"])
        assert exc_info.value.code == 1

    def test_fails_on_name_mismatch(self, tmp_path):
        self._write_package_json(tmp_path, {
            "name": "test",
            "mcpName": "io.github.user/server-a",
        })
        self._write_server_json(tmp_path, {
            "name": "io.github.user/server-b",
        })

        with pytest.raises(SystemExit) as exc_info:
            ppm_main(["--root", str(tmp_path), "publish-mcp", "--dry-run"])
        assert exc_info.value.code == 1
