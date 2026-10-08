#!/usr/bin/env python3
"""Record a batch build of this repo as JSON (never fails on build errors).

Runs tools/ci/batch_build_check.py (same unit list, flags and REQUIRED policy
as the batch-build CI job) and adds the repo HEAD, a run timestamp and the
compiler versions, so build_to_memory.py can turn the result into memory nodes.

    python tools/build_memory/batch_build.py --out build_results.json

The CI job's batch-build-results.json artifact has the same unit schema and
can be fed to build_to_memory.py directly.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _cmd(args):
    try:
        return subprocess.run(args, cwd=str(ROOT), capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception:
        return ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="build_results.json")
    args = ap.parse_args(argv)
    spec = importlib.util.spec_from_file_location("batch_build_check", ROOT / "tools" / "ci" / "batch_build_check.py")
    bbc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bbc)
    old_argv = sys.argv
    sys.argv = ["batch_build_check.py", "--json", args.out]
    try:
        rc = bbc.main()
    finally:
        sys.argv = old_argv
    data = json.loads(Path(args.out).read_text())
    data["meta"] = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "repo": ROOT.name,
        "head": _cmd(["git", "rev-parse", "HEAD"]),
        "gcc": (_cmd(["gcc", "--version"]).splitlines() or [""])[0],
        "cython": _cmd([sys.executable, "-m", "cython", "--version"]),
        "required_check_exit": rc,
    }
    Path(args.out).write_text(json.dumps(data, indent=1))
    print(f"wrote {args.out} (required-check exit code {rc}; recorded, not enforced here)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
