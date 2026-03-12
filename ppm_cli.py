"""
ppm_cli — Entry point for the ``ppm`` console command.

Delegates to the full CLI implementation in Ppm-lib/Ppm-cli.py.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import urllib.error


def _project_paths(root):
    ppm_dir = os.path.join(root, ".ppm")
    return {
        "ppm_dir": ppm_dir,
        "lock": os.path.join(ppm_dir, "lock.json"),
        "ledger": os.path.join(ppm_dir, "ledger.jsonl"),
        "state": os.path.join(ppm_dir, "state.json"),
    }


def _ensure_init(root):
    p = _project_paths(root)
    os.makedirs(p["ppm_dir"], exist_ok=True)
    for path in [p["lock"], p["ledger"], p["state"]]:
        if not os.path.exists(path):
            if path.endswith(".json"):
                with open(path, "w") as f:
                    json.dump({}, f)
            else:
                open(path, "a").close()
    return p


def cmd_resolve(args):
    """Stub resolve — creates/updates PPM.lock from PPM.toml."""
    root = args.root
    toml_path = os.path.join(root, "PPM.toml")
    lock_path = os.path.join(root, "PPM.lock")

    deps = {}
    if os.path.exists(toml_path):
        with open(toml_path, "r") as f:
            content = f.read()
        # Minimal TOML parser for [tool.ppm.dependencies]
        in_deps = False
        for line in content.splitlines():
            stripped = line.strip()
            if stripped == "[tool.ppm.dependencies]":
                in_deps = True
                continue
            if stripped.startswith("[") and in_deps:
                in_deps = False
                continue
            if in_deps and "=" in stripped and not stripped.startswith("#"):
                key, val = stripped.split("=", 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                deps[key] = {"version": val, "resolved": True}

    lock = {"packages": deps, "metadata": {"generator": "ppm", "version": "0.0.3-dev"}}
    with open(lock_path, "w") as f:
        json.dump(lock, f, indent=2, sort_keys=True)
    print(f"Resolved {len(deps)} dependencies → {lock_path}")


def cmd_lock(args):
    """Verify/update the lock file."""
    root = args.root
    lock_path = os.path.join(root, "PPM.lock")
    if os.path.exists(lock_path):
        with open(lock_path, "r") as f:
            lock = json.load(f)
        print(f"Lock file present with {len(lock.get('packages', {}))} packages.")
    else:
        print("No PPM.lock found. Run `ppm resolve` first.")
        sys.exit(1)


def cmd_doctor(args):
    """Diagnose the project environment."""
    root = args.root
    issues = []

    # Check PPM.toml
    toml_path = os.path.join(root, "PPM.toml")
    if os.path.exists(toml_path):
        print("✅  PPM.toml found")
    else:
        print("❌  PPM.toml not found")
        issues.append("missing PPM.toml")

    # Check PPM.lock
    lock_path = os.path.join(root, "PPM.lock")
    if os.path.exists(lock_path):
        print("✅  PPM.lock found")
    else:
        print("⚠️  PPM.lock not found (run `ppm resolve`)")

    # Check Python
    print(f"✅  Python {sys.version.split()[0]}")

    # Check C compiler
    if os.system("cc --version >/dev/null 2>&1") == 0:
        print("✅  C compiler available")
    else:
        print("❌  No C compiler in PATH")
        issues.append("no C compiler")

    if args.explain:
        if issues:
            print(f"\n📋  Issues: {', '.join(issues)}")
        else:
            print("\n📋  No issues found.")

    if args.fail_on_red and issues:
        sys.exit(1)

    print(f"\n🏁  Doctor complete ({len(issues)} issue{'s' if len(issues) != 1 else ''} found)")


def _read_json_field(json_path, *keys):
    """Read a nested field from a JSON file. Returns None if not found."""
    if not os.path.exists(json_path):
        return None
    try:
        with open(json_path, "r") as f:
            data = json.load(f)
        for key in keys:
            if not isinstance(data, dict):
                return None
            data = data.get(key)
            if data is None:
                return None
        return data
    except (json.JSONDecodeError, OSError):
        return None


def _validate_mcp_name(mcp_name):
    """Validate an mcpName value.

    Returns a list of error strings (empty if valid).
    """
    errors = []
    if not mcp_name:
        errors.append("mcpName is empty or missing")
        return errors
    if "/" not in mcp_name:
        errors.append(
            f"mcpName '{mcp_name}' must contain a '/' separator "
            "(e.g. 'io.github.username/server-name')"
        )
    elif not mcp_name.startswith("io.github."):
        errors.append(
            f"mcpName '{mcp_name}' should start with 'io.github.<username>/' "
            "for GitHub-based authentication"
        )
    return errors


def cmd_validate_mcp(args):
    """Validate MCP Registry metadata in package.json and mcp_manifest.json."""
    root = args.root
    issues = []

    # Check package.json
    pkg_path = os.path.join(root, "package.json")
    mcp_name_pkg = _read_json_field(pkg_path, "mcpName")
    if os.path.exists(pkg_path):
        if mcp_name_pkg:
            print(f"✅  package.json mcpName: {mcp_name_pkg}")
            errs = _validate_mcp_name(mcp_name_pkg)
            for e in errs:
                print(f"❌  {e}")
                issues.append(e)
        else:
            msg = "package.json missing 'mcpName' property"
            print(f"❌  {msg}")
            issues.append(msg)

        # Check description
        desc = _read_json_field(pkg_path, "description")
        if desc:
            display = f"{desc[:60]}…" if len(desc) > 60 else desc
            print(f"✅  package.json description: {display}")
        else:
            msg = "package.json 'description' is empty"
            print(f"⚠️  {msg}")
            issues.append(msg)

        # Check repository
        repo_url = _read_json_field(pkg_path, "repository", "url")
        if repo_url:
            print(f"✅  package.json repository: {repo_url}")
        else:
            msg = "package.json missing 'repository.url'"
            print(f"⚠️  {msg}")
            issues.append(msg)
    else:
        msg = "package.json not found"
        print(f"❌  {msg}")
        issues.append(msg)

    # Check mcp_manifest.json
    manifest_path = os.path.join(root, "mcp", "mcp_manifest.json")
    if os.path.exists(manifest_path):
        mcp_name_manifest = _read_json_field(manifest_path, "mcpName")
        if mcp_name_manifest:
            print(f"✅  mcp_manifest.json mcpName: {mcp_name_manifest}")
            if mcp_name_pkg and mcp_name_manifest != mcp_name_pkg:
                msg = (
                    f"mcpName mismatch: package.json has '{mcp_name_pkg}' "
                    f"but mcp_manifest.json has '{mcp_name_manifest}'"
                )
                print(f"❌  {msg}")
                issues.append(msg)
        else:
            print("⚠️  mcp_manifest.json missing 'mcpName' (optional)")
    else:
        print("ℹ️  mcp/mcp_manifest.json not found (optional)")

    # Check server.json
    server_json_path = os.path.join(root, "server.json")
    if os.path.exists(server_json_path):
        server_name = _read_json_field(server_json_path, "name")
        if server_name:
            print(f"✅  server.json name: {server_name}")
            if mcp_name_pkg and server_name != mcp_name_pkg:
                msg = (
                    f"server.json name mismatch: package.json mcpName is "
                    f"'{mcp_name_pkg}' but server.json name is '{server_name}'"
                )
                print(f"❌  {msg}")
                issues.append(msg)
        else:
            msg = "server.json missing 'name' property"
            print(f"❌  {msg}")
            issues.append(msg)
    else:
        print("ℹ️  server.json not found (run `ppm init-mcp` to generate)")

    if issues:
        print(f"\n📋  {len(issues)} issue(s) found")
        if args.fail_on_error:
            sys.exit(1)
    else:
        print("\n✅  MCP Registry metadata is valid")


def cmd_init_mcp(args):
    """Generate a server.json file for MCP Registry publishing.

    Reads metadata from package.json and produces the server.json template
    that ``mcp-publisher publish`` expects.
    """
    root = args.root
    out_path = os.path.join(root, "server.json")

    if os.path.exists(out_path) and not args.force:
        print(f"server.json already exists at {out_path}")
        print("Use --force to overwrite.")
        sys.exit(1)

    pkg_path = os.path.join(root, "package.json")
    if not os.path.exists(pkg_path):
        print("Error: package.json not found. Cannot generate server.json.",
              file=sys.stderr)
        sys.exit(1)

    mcp_name = _read_json_field(pkg_path, "mcpName")
    if not mcp_name:
        print("Error: package.json missing 'mcpName'. "
              "Add it before generating server.json.",
              file=sys.stderr)
        sys.exit(1)

    pkg_name = _read_json_field(pkg_path, "name") or ""
    version = _read_json_field(pkg_path, "version") or "0.0.0"
    description = _read_json_field(pkg_path, "description") or ""
    repo_url = _read_json_field(pkg_path, "repository", "url") or ""
    # Normalize git+https:// URLs to plain https://
    if repo_url.startswith("git+"):
        repo_url = repo_url[4:]
    if repo_url.endswith(".git"):
        repo_url = repo_url[:-4]

    server = {
        "$schema": "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json",
        "name": mcp_name,
        "description": description,
        "repository": {
            "url": repo_url,
            "source": "github",
        },
        "version": version,
        "packages": [
            {
                "registryType": "npm",
                "identifier": pkg_name,
                "version": version,
                "transport": {
                    "type": "stdio",
                },
            }
        ],
    }

    with open(out_path, "w") as f:
        json.dump(server, f, indent=2)
        f.write("\n")

    print(f"✅  Generated {out_path}")
    print(f"    name: {mcp_name}")
    print(f"    version: {version}")
    print(f"    package: {pkg_name}")
    print("\nReview server.json, then run `ppm publish-mcp` to publish.")


def cmd_publish_mcp(args):
    """Publish the MCP server to the MCP Registry via mcp-publisher.

    Pre-flight: validates metadata and checks for server.json, then
    delegates to the external ``mcp-publisher publish`` CLI.
    """
    root = args.root

    # --- pre-flight validation ------------------------------------------------
    pkg_path = os.path.join(root, "package.json")
    mcp_name = _read_json_field(pkg_path, "mcpName")
    if not mcp_name:
        print("Error: package.json missing 'mcpName'. "
              "Run `ppm validate-mcp` for details.",
              file=sys.stderr)
        sys.exit(1)

    server_json_path = os.path.join(root, "server.json")
    if not os.path.exists(server_json_path):
        print("Error: server.json not found. "
              "Run `ppm init-mcp` to generate it.",
              file=sys.stderr)
        sys.exit(1)

    server_name = _read_json_field(server_json_path, "name")
    if server_name != mcp_name:
        print(f"Error: server.json name '{server_name}' does not match "
              f"package.json mcpName '{mcp_name}'.",
              file=sys.stderr)
        sys.exit(1)

    # --- check mcp-publisher is available ------------------------------------
    if not args.dry_run:
        if shutil.which("mcp-publisher") is None:
            print(
                "Error: mcp-publisher not found in PATH.\n"
                "Install it with:\n"
                '  curl -L "https://github.com/modelcontextprotocol/registry/'
                'releases/latest/download/mcp-publisher_$(uname -s | '
                "tr '[:upper:]' '[:lower:]')_$(uname -m | "
                "sed 's/x86_64/amd64/;s/aarch64/arm64/').tar.gz\" "
                "| tar xz mcp-publisher && sudo mv mcp-publisher /usr/local/bin/",
                file=sys.stderr,
            )
            sys.exit(1)

    print(f"Publishing {mcp_name} to MCP Registry …")

    if args.dry_run:
        print("(dry-run) Would run: mcp-publisher publish")
        print(f"  server.json: {server_json_path}")
        print("Dry-run complete — no changes made.")
        return

    result = subprocess.run(
        ["mcp-publisher", "publish"],
        cwd=root,
    )
    sys.exit(result.returncode)


def cmd_build(args):
    """Build wheels from the current project using pip wheel."""
    out = args.out or "dist/"
    root = getattr(args, "root", ".")
    os.makedirs(out, exist_ok=True)

    # Run pip wheel to produce a .whl for the local project
    cmd = [sys.executable, "-m", "pip", "wheel", "--no-deps", "--wheel-dir", out, root]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Build failed:\n{result.stderr}", file=sys.stderr)
        sys.exit(result.returncode)

    wheels = [f for f in os.listdir(out) if f.endswith(".whl")]
    print(f"Built {len(wheels)} wheel(s) → {out}")


def cmd_install(args):
    """Install packages from PPM.lock, optionally preferring a local wheelhouse."""
    root = getattr(args, "root", ".")
    lock_path = os.path.join(root, "PPM.lock")
    prefer = getattr(args, "prefer", None)

    if not os.path.exists(lock_path):
        print(f"No PPM.lock found at {lock_path}. Run `ppm resolve` first.")
        sys.exit(1)

    with open(lock_path, "r") as f:
        lock = json.load(f)

    packages = lock.get("packages", {})
    if not packages:
        print("Lock file contains no packages.")
        return

    # Build a spec list: "name==version" where a version is recorded
    specs = []
    for name, meta in packages.items():
        version = meta.get("version", "") if isinstance(meta, dict) else ""
        specs.append(f"{name}=={version}" if version else name)

    cmd = [sys.executable, "-m", "pip", "install"]
    if prefer and os.path.isdir(prefer):
        # Prefer pre-built wheels from the wheelhouse (offline-first)
        cmd += ["--find-links", prefer, "--prefer-binary"]
    cmd += specs

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Install failed:\n{result.stderr}", file=sys.stderr)
        sys.exit(result.returncode)

    print(f"Installed {len(specs)} package(s)")


def cmd_run(args):
    """Run a script defined in PPM.toml."""
    script = args.script
    if script == "test":
        os.execvp("pytest", ["pytest", "-q"])
    else:
        print(f"Unknown script: {script}")
        sys.exit(1)


def _read_toml_field(toml_path, section_prefix, key):
    """Minimal TOML reader: extract a key from lines under [section_prefix]."""
    if not os.path.exists(toml_path):
        return None
    in_section = False
    with open(toml_path, "r") as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith("["):
                in_section = stripped.startswith(f"[{section_prefix}]")
                continue
            if in_section and "=" in stripped and not stripped.startswith("#"):
                k, v = stripped.split("=", 1)
                if k.strip() == key:
                    return v.strip().strip('"').strip("'")
    return None


def _sha256_file(path):
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _discover_wheels(wheelhouse):
    """Return sorted list of .whl file paths in the wheelhouse directory."""
    if not os.path.isdir(wheelhouse):
        return []
    return sorted(
        os.path.join(wheelhouse, f)
        for f in os.listdir(wheelhouse)
        if f.endswith(".whl")
    )


def _multipart_encode(fields, files):
    """Build a multipart/form-data body from fields and files.

    Returns (body_bytes, content_type).
    """
    boundary = "----PPMPublishBoundary"
    parts = []
    for key, value in fields.items():
        parts.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{key}"\r\n\r\n'
            f"{value}\r\n"
        )
    for key, (filename, data) in files.items():
        parts.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{key}"; filename="{filename}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n"
        )
        parts.append(None)  # placeholder for binary data
        parts.append("\r\n")
    parts.append(f"--{boundary}--\r\n")

    body = b""
    file_iter = iter(files.values())
    for part in parts:
        if part is None:
            _, data = next(file_iter)
            body += data
        else:
            body += part.encode("utf-8")

    content_type = f"multipart/form-data; boundary={boundary}"
    return body, content_type


def cmd_publish(args):
    """Publish wheels to the PPM registry."""
    root = args.root
    toml_path = os.path.join(root, "PPM.toml")

    # Resolve registry URL and token (CLI flags > env vars > PPM.toml)
    registry = args.registry or os.environ.get("PPM_REGISTRY_URL")
    token = args.token or os.environ.get("PPM_REGISTRY_TOKEN")
    wheelhouse = args.wheelhouse or os.path.join(root, "dist")

    if not registry:
        # Try PPM.toml
        registry = _read_toml_field(toml_path, "tool.ppm", "registry")
    if not registry:
        print("Error: no registry URL provided. "
              "Use --registry, set PPM_REGISTRY_URL, "
              "or configure [tool.ppm] registry in PPM.toml.",
              file=sys.stderr)
        sys.exit(1)

    if not token:
        print("Error: no registry token provided. "
              "Use --token or set PPM_REGISTRY_TOKEN.",
              file=sys.stderr)
        sys.exit(1)

    # Read project metadata
    project_name = _read_toml_field(toml_path, "project", "name") or "unknown"
    project_version = _read_toml_field(toml_path, "project", "version") or "0.0.0"

    # Discover wheels
    wheels = _discover_wheels(wheelhouse)
    if not wheels:
        print(f"No .whl files found in {wheelhouse}; nothing to publish.")
        sys.exit(0)

    print(f"Publishing {project_name}=={project_version} "
          f"to {registry}")
    print(f"Found {len(wheels)} wheel(s) in {wheelhouse}")

    upload_url = registry.rstrip("/") + "/api/v1/upload"
    ok_count = 0
    fail_count = 0

    for whl_path in wheels:
        filename = os.path.basename(whl_path)
        sha256 = _sha256_file(whl_path)
        with open(whl_path, "rb") as f:
            whl_data = f.read()

        fields = {
            "name": project_name,
            "version": project_version,
            "sha256": sha256,
        }
        files = {
            "wheel": (filename, whl_data),
        }

        body, content_type = _multipart_encode(fields, files)

        req = urllib.request.Request(
            upload_url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": content_type,
                "User-Agent": "ppm-cli/0.0.3",
            },
        )

        print(f"  ⬆️  {filename} ({sha256[:12]}…) → {upload_url}")
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                status = resp.status
                resp_body = resp.read().decode("utf-8", errors="replace")
            print(f"      ✅ {status} — {resp_body[:200]}")
            ok_count += 1
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            print(f"      ❌ HTTP {exc.code}: {err_body[:200]}",
                  file=sys.stderr)
            fail_count += 1
        except urllib.error.URLError as exc:
            print(f"      ❌ Connection error: {exc.reason}",
                  file=sys.stderr)
            fail_count += 1

    print(f"\n🏁 Published {ok_count}/{len(wheels)} wheel(s)"
          + (f" ({fail_count} failed)" if fail_count else ""))
    if fail_count:
        sys.exit(1)


def build_parser():
    ap = argparse.ArgumentParser(prog="ppm", description="PPM — Python Package Manager")
    ap.add_argument("--root", default=".", help="Project root directory")

    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("resolve").set_defaults(func=cmd_resolve)
    sub.add_parser("lock").set_defaults(func=cmd_lock)

    p = sub.add_parser("doctor")
    p.add_argument("--explain", action="store_true")
    p.add_argument("--fail-on-red", action="store_true")
    p.add_argument("--fix", action="store_true")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("build")
    p.add_argument("--wheel", action="store_true")
    p.add_argument("--out", default=None)
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("install")
    p.add_argument("--prefer", default=None)
    p.set_defaults(func=cmd_install)

    p = sub.add_parser("run")
    p.add_argument("script")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("publish")
    p.add_argument("--registry", default=None)
    p.add_argument("--token", default=None)
    p.add_argument("--wheelhouse", default=None)
    p.set_defaults(func=cmd_publish)

    p = sub.add_parser("validate-mcp",
                        help="Validate MCP Registry metadata")
    p.add_argument("--fail-on-error", action="store_true",
                   help="Exit with error if validation fails")
    p.set_defaults(func=cmd_validate_mcp)

    p = sub.add_parser("init-mcp",
                        help="Generate server.json for MCP Registry publishing")
    p.add_argument("--force", action="store_true",
                   help="Overwrite existing server.json")
    p.set_defaults(func=cmd_init_mcp)

    p = sub.add_parser("publish-mcp",
                        help="Publish MCP server to the MCP Registry")
    p.add_argument("--dry-run", action="store_true",
                   help="Validate and show what would be published without publishing")
    p.set_defaults(func=cmd_publish_mcp)

    return ap


def main(argv=None):
    argv = argv or sys.argv[1:]
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.cmd:
        parser.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
