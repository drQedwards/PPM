#!/usr/bin/env python3
"""Package-level batch build of a Go module, recorded in the unit schema that
build_to_memory.py reads (never fails on build errors).

    python tools/build_memory/go_batch_build.py /path/to/go/module --out go_build_results.json
    python tools/build_memory/build_to_memory.py go_build_results.json \\
        --root /path/to/go/module --group toplevel --load-sqlite graph.sqlite3

One unit per package from ``go list -e -json ./...``:

  path              package directory, relative to the module root ("." for the root)
  sha256            build_to_memory.files_sha256 over ``files``
  files             the package's Go/cgo/test/C/H/asm files, plus C/H files its cgo
                    preamble pulls in with ``#include "..."`` (resolved recursively
                    inside the module)
  includes          those cgo include files (become header nodes + depends_on edges)
  depends_on_units  package directories of intra-module imports (incl. test imports)
  kind              "go" or "cgo"
  ok                build_ok and vet_ok
  build_ok          ``go build -o /dev/null ./pkg`` (no binaries are written into
                    the checkout); a test-only package counts as ok
  vet_ok, warnings  ``go vet ./pkg`` and its diagnostic count (``--no-vet`` skips it)
  first_errors      first lines of build/vet errors

Nothing in the target module is modified.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("build_to_memory", _HERE / "build_to_memory.py")
btm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(btm)

INCLUDE_RE = re.compile(r'#\s*include\s+"([^"]+)"')
FILE_KEYS = ("GoFiles", "CgoFiles", "TestGoFiles", "XTestGoFiles", "CFiles", "HFiles", "SFiles")
DIAG_RE = re.compile(r"^\S+\.go:\d+:\d+: ")


def go_available() -> bool:
    return shutil.which("go") is not None


def _run(args: List[str], cwd: Path, timeout: int = 1800) -> Tuple[int, str, float]:
    t = time.time()
    try:
        p = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout + p.stderr, time.time() - t
    except subprocess.TimeoutExpired:
        return 124, f"timeout after {timeout}s", time.time() - t


def go_list(root: Path) -> List[Dict[str, Any]]:
    """Packages of the module at ``root`` (``go list -e -json ./...``)."""
    p = subprocess.run(["go", "list", "-e", "-json", "./..."], cwd=str(root),
                       capture_output=True, text=True)
    if p.returncode != 0 and not p.stdout.strip():
        raise RuntimeError(f"go list failed in {root}: {p.stderr.strip()[:500]}")
    out, dec, i, pkgs = p.stdout, json.JSONDecoder(), 0, []
    while i < len(out):
        while i < len(out) and out[i].isspace():
            i += 1
        if i >= len(out):
            break
        obj, i = dec.raw_decode(out, i)
        pkgs.append(obj)
    real = [q for q in pkgs if q.get("Dir")]
    if not real:
        errs = [(q.get("Error") or {}).get("Err", "") for q in pkgs]
        detail = "; ".join(e for e in errs if e) or p.stderr.strip()[:500] or "no packages"
        raise RuntimeError(f"go list found no packages in {root}: {detail}")
    return real


def _cgo_includes(start: List[Path], root: Path) -> List[Path]:
    seen: Dict[Path, None] = {}
    todo = list(start)
    while todo:
        f = todo.pop()
        for inc in INCLUDE_RE.findall(f.read_text(errors="replace")):
            c = (f.parent / inc).resolve()
            if c.is_file() and c.is_relative_to(root) and c not in seen:
                seen[c] = None
                todo.append(c)
    return sorted(seen)


def package_units(root: Path) -> List[Dict[str, Any]]:
    """Units (without build results) for every package of the module."""
    root = root.resolve()
    pkgs = go_list(root)
    module = next((p["Module"]["Path"] for p in pkgs if p.get("Module")), "")
    dir_of = {p["ImportPath"]: (Path(p["Dir"]).resolve().relative_to(root).as_posix() or ".") for p in pkgs}
    units = []
    for p in pkgs:
        d = Path(p["Dir"]).resolve()
        rel = dir_of[p["ImportPath"]]
        own = [(d / f).relative_to(root).as_posix() for k in FILE_KEYS for f in p.get(k, [])]
        inc = [c.relative_to(root).as_posix()
               for c in _cgo_includes([d / f for f in p.get("CgoFiles", [])], root)]
        files = sorted(set(own) | set(inc))
        imports = set(p.get("Imports", []) + p.get("TestImports", []) + p.get("XTestImports", []))
        deps = sorted({dir_of[i] for i in imports if i in dir_of and dir_of[i] != rel})
        units.append({
            "path": rel, "import_path": p["ImportPath"], "module": module,
            "sha256": btm.files_sha256(root, files), "files": files, "includes": inc,
            "depends_on_units": deps, "kind": "cgo" if p.get("CgoFiles") else "go",
            "required": False, "list_error": (p.get("Error") or {}).get("Err", ""),
        })
    return units


def build_unit(root: Path, u: Dict[str, Any], vet: bool = True) -> Dict[str, Any]:
    target = "./" + u["path"] if u["path"] != "." else "."
    rc_b, out_b, tb = _run(["go", "build", "-o", os.devnull, target], root)
    test_only = rc_b != 0 and "no non-test Go files" in out_b
    build_ok = test_only or rc_b == 0
    rc_v, out_v, tv = _run(["go", "vet", target], root) if vet else (0, "", 0.0)
    errs = [ln for ln in ((out_b.splitlines() if not build_ok else []) +
                          (out_v.splitlines() if rc_v else []))
            if ln and not ln.startswith("#")]
    u.update(build_ok=build_ok, test_only=test_only, vet_ok=None if not vet else rc_v == 0,
             ok=build_ok and rc_v == 0, warnings=sum(1 for ln in out_v.splitlines() if DIAG_RE.match(ln)),
             first_errors=errs[:5], build_s=round(tb, 2), vet_s=round(tv, 2))
    return u


def go_package_hasher(root: Path) -> Callable[[Path, Dict[str, str]], str]:
    """A stale_paths hasher that re-lists packages, so added or removed
    files are noticed too (the stored ``files`` list alone cannot see a new file)."""
    current = {u["path"]: u["sha256"] for u in package_units(root)}

    def hasher(_root: Path, md: Dict[str, str]) -> str:
        return current.get(md["path"], "missing")
    return hasher


def run(root: Path, jobs: int = 4, vet: bool = True) -> Dict[str, Any]:
    root = root.resolve()
    t0 = time.time()
    units = package_units(root)
    t_list = time.time() - t0
    t1 = time.time()
    with ThreadPoolExecutor(max(1, jobs)) as ex:
        units = list(ex.map(lambda u: build_unit(root, u, vet), units))
    t_units = time.time() - t1
    head = _run(["git", "rev-parse", "HEAD"], root)
    return {
        "units": units, "required_failures": 0,
        "meta": {
            "repo": root.name, "module": units[0]["module"] if units else "",
            "head": head[1].strip() if head[0] == 0 else "",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "go": _run(["go", "version"], root)[1].strip(),
            "gcc": (_run(["gcc", "--version"], root)[1].splitlines() or [""])[0],
            "go_list_s": round(t_list, 2), "build_wall_s": round(t_units, 2), "jobs": jobs, "vet": vet,
        },
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Package-level batch build of a Go module (records, never fails).")
    ap.add_argument("root", help="Go module root")
    ap.add_argument("--out", default="go_build_results.json")
    ap.add_argument("-j", "--jobs", type=int, default=4)
    ap.add_argument("--no-vet", action="store_true", help="skip go vet")
    args = ap.parse_args(argv)
    if not go_available():
        print("go not found on PATH", file=sys.stderr)
        return 2
    res = run(Path(args.root), args.jobs, not args.no_vet)
    Path(args.out).write_text(json.dumps(res, indent=1))
    u = res["units"]
    print(f"{len(u)} packages: {sum(x['ok'] for x in u)} ok (build {sum(x['build_ok'] for x in u)}); "
          f"go list {res['meta']['go_list_s']}s, build wall {res['meta']['build_wall_s']}s (-j{args.jobs}) -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
