"""
ppm-panda-lib : pandas.py
----------------------------------
High-level helpers (and CLI) for the `panda` PPM plugin.

Usage from shell
----------------
# install pandas (latest)
python -m ppm_panda_lib.pandas install

# install a specific version
python -m ppm_panda_lib.pandas install 2.2.2

# cache all wheels defined in wheels.lock
python -m ppm_panda_lib.pandas wheel-cache

# quick CSV preview
python -m ppm_panda_lib.pandas csv-peek data.csv

# environment sanity-check
python -m ppm_panda_lib.pandas doctor
"""

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple, Optional

try:
    import pandas as _pd  # noqa: F401  (may be missing before first install)
except ModuleNotFoundError:
    _pd = None  # type: ignore

ROOT = Path(__file__).resolve().parent
WHEELS_LOCK = ROOT / "wheels.lock"


# ──────────────────────────────────────────────────────────────────────────────
# helpers
# ──────────────────────────────────────────────────────────────────────────────
def _sha256sum(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_lock() -> List[Tuple[str, str, str]]:
    """Parse wheels.lock → [(name, version, sha256)]"""
    if not WHEELS_LOCK.exists():
        return []
    name = version = sha = None
    out: List[Tuple[str, str, str]] = []
    for line in WHEELS_LOCK.read_text().splitlines():
        line = line.strip()
        if line.startswith("name"):
            name = line.split("=", 1)[1].strip().strip('"')
        elif line.startswith("version"):
            version = line.split("=", 1)[1].strip().strip('"')
        elif line.startswith("sha256"):
            sha = line.split("=", 1)[1].strip().strip('"')
            if name and version and sha:
                out.append((name, version, sha))
                name = version = sha = None
    return out


# ──────────────────────────────────────────────────────────────────────────────
# core actions (called by the C bridge OR from CLI)
# ──────────────────────────────────────────────────────────────────────────────
def install(ver: Optional[str] = None) -> None:
    """Install pandas (and deps) deterministically."""
    pkg = "pandas" if ver is None else f"pandas=={ver}"
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "--no-cache-dir", "--upgrade", pkg]
    )
    print(f"✓ installed {pkg}")


def cache() -> None:
    """Pre-download wheels listed in wheels.lock to ./wheelhouse/"""
    triples = _read_lock()
    if not triples:
        print("! wheels.lock missing (nothing to cache)")
        return
    wheelhouse = ROOT / "wheelhouse"
    wheelhouse.mkdir(exist_ok=True)
    for name, version, sha in triples:
        target = wheelhouse / f"{name}-{version}-py3-none-any.whl"
        if target.exists() and _sha256sum(target) == sha:
            print(f"✓ {target.name} ok")
            continue
        print(f"↓ {name}=={version}")
        subprocess.check_call(
            [
                sys.executable,
                "-m",
                "pip",
                "download",
                "--only-binary=:all:",
                "--no-deps",
                "--dest",
                str(wheelhouse),
                f"{name}=={version}",
            ]
        )
        if _sha256sum(target) != sha:
            raise RuntimeError(f"SHA mismatch for {target.name}")
    print(f"✓ wheel cache ready → {wheelhouse}")


def csv_peek(path: str, nrows: int = 10) -> None:
    """Print a small preview & dtype summary of a CSV file."""
    if _pd is None:
        raise RuntimeError("pandas not installed — run 'panda install' first")
    df = _pd.read_csv(path, nrows=nrows)
    print(df.to_markdown())
    print("\n— dtypes —")
    print(df.dtypes)


def doctor() -> None:
    """Environment sanity-check."""
    try:
        import numpy as np  # noqa: F401
    except ModuleNotFoundError:
        np = None  # type: ignore

    print("=== panda doctor ===")
    print("python  :", platform.python_version(), "→", sys.executable)
    if _pd:
        print("pandas  :", _pd.__version__)
    else:
        print("pandas  : NOT INSTALLED")

    if np:
        print("numpy   :", np.__version__)
        try:
            from numpy.__config__ import show as _show

            _show()
        except Exception:
            pass
    else:
        print("numpy   : NOT INSTALLED")
    print("platform:", platform.platform())
    print("====================")


# ──────────────────────────────────────────────────────────────────────────────
# CLI entry-point (keeps standalone flexibility)
# ──────────────────────────────────────────────────────────────────────────────
def _main() -> None:
    ap = argparse.ArgumentParser(prog="ppm panda")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_i = sub.add_parser("install", help="install pandas into workspace")
    p_i.add_argument("version", nargs="?", help="specific version (optional)")

    sub.add_parser("wheel-cache", help="pre-fetch wheels")

    p_csv = sub.add_parser("csv-peek", help="preview a CSV")
    p_csv.add_argument("csv_path")
    p_csv.add_argument("--n", type=int, default=10, help="rows to display (default 10)")

    sub.add_parser("doctor", help="diagnose env")

    args = ap.parse_args()
    if args.cmd == "install":
        install(args.version)
    elif args.cmd == "wheel-cache":
        cache()
    elif args.cmd == "csv-peek":
        csv_peek(args.csv_path, args.n)
    elif args.cmd == "doctor":
        doctor()
    else:
        ap.error("unknown sub-command")


if __name__ == "__main__":
    _main()
