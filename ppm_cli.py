"""
ppm_cli — Entry point for the ``ppm`` console command.

Delegates to the full CLI implementation in Ppm-lib/Ppm-cli.py.
"""
from __future__ import annotations

import argparse
import json
import os
import sys


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


def cmd_publish(args):
    """Publish to registry (stub)."""
    print("Publish: stub — no registry configured")


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
