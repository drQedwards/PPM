"""
ppm_cli — Entry point for the ``ppm`` console command.

Delegates to the full CLI implementation in Ppm-lib/Ppm-cli.py.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
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


def cmd_build(args):
    """Build wheels (stub)."""
    out = args.out or "dist/"
    os.makedirs(out, exist_ok=True)
    print(f"Build output → {out} (stub — no packages to build yet)")


def cmd_install(args):
    """Install from lock (stub)."""
    print("Install: reading lock file... (stub)")


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
