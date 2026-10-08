#!/usr/bin/env python3
"""Batch-compile every C / C++ / Cython unit in this repo and report per unit.

Policy (see tools/ci/README.md):
  * REQUIRED units must compile (and link / pass, where listed). A failure
    there fails the job.
  * Every other unit is INFORMATIONAL: compiled and reported, never fatal.
    Known-failing units (CLI/CLI.c, Ppm-lib/Pypm.c, Torch, Pandas_bridge.pyx,
    Pypm.pyx, CUDA without nvcc) live here until they are fixed.

Usage:  python tools/ci/batch_build_check.py [--json out.json]
Exit code: 0 when every REQUIRED unit passes, 1 otherwise.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import sysconfig
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
SKIP_DIRS = re.compile(r"(^|/)(node_modules|vendor|third[_-]party|build|dist|\.git)(/|$)", re.I)

# Units that must compile with -Wall -Wextra (-c). Paths are repo-relative.
REQUIRED_C = [
    "PMLL.c", "PMLL2.c", "SAT.c", "Ppm.c", "Pypm.c",
    "tests/sat_c_driver.c",
    "Q_promise_lib/Promises.c", "Q_promise_lib/Q_promises.c",
    "Q_promise_lib/qpromise.c", "Q_promise_lib/test_qpromise.c",
    "Numpy-lib/Numpy.c", "Resolver-lib/Importresolver.c",
    "Panda-lib/Panda.c", "Panda-lib/Panda_py.c", "Panda-lib/Pandas.c",
    "Transformer-lib/Transformer.c",
]
REQUIRED_CXX = ["solution.cpp", "CLI/LLM-CLI-BUILDER-PPM.cpp", "Ppm-lib/Pypm.cpp"]
REQUIRED_PYX = [
    "SAT.pyx", "Q_promise_lib/Q_promises.pyx", "Numpy-lib/Numpy.pyx",
    "Resolver-lib/Importresolver.pyx", "CLI/CLI.pyx",
]
# Executables that must link (sources, extra flags); "run" ones must exit 0.
REQUIRED_LINKS = [
    {"name": "PMLL", "sources": ["PMLL.c"], "flags": ["-lm"]},
    {"name": "PMLL2-selftest", "sources": ["PMLL2.c"], "flags": ["-DPMLL2_TEST"], "run": True},
    {"name": "SAT", "sources": ["SAT.c"], "flags": ["-lm"]},
    {"name": "sat_c_driver", "sources": ["tests/sat_c_driver.c", "SAT.c"], "flags": ["-DSAT_NO_MAIN", "-lm"]},
    {"name": "qpromise_demo", "sources": ["Q_promise_lib/Promises.c", "Q_promise_lib/qpromise.c", "PMLL.c"],
     "flags": ["-DPMLL_NO_MAIN", "-lm"], "run": True},
    {"name": "Ppm", "sources": ["Ppm.c"], "flags": ["-ldl", "-lcurl"]},
]
REQUIRED_MAKE = [
    {"dir": "Q_promise_lib", "targets": ["clean", "test", "clean"]},
    {"dir": "Panda-lib", "targets": ["clean", "panda.so", "clean"]},
]

PY_INC = sysconfig.get_paths()["include"]
WARN_RE = re.compile(r": warning: ")
ERR_RE = re.compile(r": (fatal )?error: |undefined reference|ld returned|^Error compiling Cython|\.pyx:\d+:\d+: ")


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _run(cmd: List[str], cwd: Path, timeout: int = 300) -> Dict[str, object]:
    try:
        r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
        out, rc = r.stdout + r.stderr, r.returncode
    except subprocess.TimeoutExpired:
        out, rc = "TIMEOUT", -9
    except FileNotFoundError as exc:
        out, rc = f"tool not found: {exc}", -2
    lines = out.splitlines()
    errs = [ln.replace(str(ROOT) + "/", "") for ln in lines if ERR_RE.search(ln)]
    errs.sort(key=lambda ln: 0 if re.search(r"\.pyx:\d+:\d+: ", ln) else 1)  # Cython: real location first
    if rc != 0 and not errs:  # e.g. a failing make recipe or self-test: keep its last output lines
        errs = [ln.replace(str(ROOT) + "/", "") for ln in lines if ln.strip()][-3:] or [f"exit code {rc}"]
    return {"ok": rc == 0, "rc": rc, "warnings": sum(1 for ln in lines if WARN_RE.search(ln)),
            "first_errors": errs[:3]}


def _numpy_include() -> Optional[str]:
    try:
        import numpy  # noqa: F401
        return numpy.get_include()
    except Exception:
        return None


def _tracked(exts) -> List[str]:
    try:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=str(ROOT), capture_output=True, text=True, check=True).stdout
        files = [f for f in out.split("\0") if f]
    except Exception:
        files = [str(p.relative_to(ROOT)) for p in ROOT.rglob("*") if p.is_file()]
    return sorted(f for f in files if f.endswith(exts) and not SKIP_DIRS.search(f))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="batch-build-results.json")
    args = ap.parse_args()
    cc = os.environ.get("CC", "gcc")
    cxx = os.environ.get("CXX", "g++")
    tmp = Path(tempfile.mkdtemp(prefix="batch-build-"))
    np_inc = _numpy_include()
    units: List[Dict[str, object]] = []

    for f in _tracked((".c", ".cpp", ".cc", ".cu", ".pyx")):
        p = ROOT / f
        inc = ["-I", str(p.parent), "-I", str(ROOT), "-I", PY_INC]
        obj = tmp / (f.replace("/", "_") + ".o")
        rec: Dict[str, object] = {"path": f, "sha256": _sha(p)}
        if f.endswith(".c"):
            rec.update(kind="c", required=f in REQUIRED_C,
                       **_run([cc, "-std=c11", "-Wall", "-Wextra", "-O1", "-c", str(p), *inc, "-o", str(obj)], p.parent))
        elif f.endswith((".cpp", ".cc")):
            rec.update(kind="c++", required=f in REQUIRED_CXX,
                       **_run([cxx, "-std=c++17", "-Wall", "-Wextra", "-O1", "-c", str(p), *inc, "-o", str(obj)], p.parent))
        elif f.endswith(".cu"):
            if shutil.which("nvcc"):
                rec.update(kind="cuda", required=False,
                           **_run(["nvcc", "-c", str(p), "-I", str(p.parent), "-o", str(obj)], p.parent))
            else:
                rec.update(kind="cuda", required=False, ok=None, rc=None, warnings=0,
                           first_errors=["skipped: nvcc not available"])
        else:  # .pyx -> Cython -> C object (output name avoids clobbering a sibling <stem>.c)
            cfile = tmp / (f.replace("/", "_") + "_cy.c")
            cy = _run([sys.executable, "-m", "cython", "-3", "-I", str(p.parent), str(p), "-o", str(cfile)], p.parent)
            if cy["ok"]:
                extra = ["-I", np_inc] if np_inc else []
                cy = _run([cc, "-Wall", "-Wextra", "-O1", "-fPIC", "-c", str(cfile), *inc, *extra, "-o", str(obj)],
                          p.parent)
            rec.update(kind="pyx", required=f in REQUIRED_PYX, **cy)
        units.append(rec)

    links = []
    for spec in REQUIRED_LINKS:
        exe = tmp / spec["name"]
        res = _run([cc, "-std=c11", "-Wall", "-Wextra", "-O1", "-I", str(ROOT), "-I", str(ROOT / "Q_promise_lib"),
                    *[str(ROOT / s) for s in spec["sources"]], "-o", str(exe), *spec["flags"]], ROOT)
        if res["ok"] and spec.get("run"):
            ran = _run([str(exe)], tmp, timeout=60)
            res = dict(res, ok=ran["ok"], ran=True, first_errors=ran["first_errors"] if not ran["ok"] else [])
        links.append(dict(name=spec["name"], required=True, **res))

    makes = []
    for spec in REQUIRED_MAKE:
        for t in spec["targets"]:
            makes.append(dict(dir=spec["dir"], target=t, required=True,
                              **_run(["make", "-C", str(ROOT / spec["dir"]), t], ROOT)))

    shutil.rmtree(tmp, ignore_errors=True)
    listed = set(REQUIRED_C) | set(REQUIRED_CXX) | set(REQUIRED_PYX)
    missing = sorted(listed - {u["path"] for u in units})
    req_fail = [u for u in units if u["required"] and not u["ok"]] + \
               [x for x in links + makes if not x["ok"]]
    info_fail = [u for u in units if not u["required"] and u["ok"] is not True]

    result = {"units": units, "links": links, "makes": makes, "missing_required": missing,
              "required_failures": len(req_fail) + len(missing), "informational_failures": len(info_fail)}
    Path(args.json).write_text(json.dumps(result, indent=1))

    lines = ["## Batch build", "",
             f"Units: {len(units)} | required: {sum(1 for u in units if u['required'])} | "
             f"OK: {sum(1 for u in units if u['ok'])} | required failures: {result['required_failures']} | "
             f"informational failures: {len(info_fail)}", "",
             "| unit | kind | required | status | warnings | first error | sha256 |", "|---|---|---|---|---|---|---|"]
    for u in units:
        status = "skipped" if u["ok"] is None else ("ok" if u["ok"] else "FAIL")
        err = (u["first_errors"] or [""])[0].replace("|", "\\|")[:140]
        lines.append(f"| `{u['path']}` | {u['kind']} | {'yes' if u['required'] else 'info'} | {status} | "
                     f"{u['warnings']} | {err} | `{str(u['sha256'])[:12]}` |")
    lines += ["", "| link / make | status | first error |", "|---|---|---|"]
    for x in links:
        lines.append(f"| link `{x['name']}`{' (+run)' if x.get('ran') else ''} | {'ok' if x['ok'] else 'FAIL'} | "
                     f"{(x['first_errors'] or [''])[0][:140]} |")
    for x in makes:
        lines.append(f"| make -C {x['dir']} {x['target']} | {'ok' if x['ok'] else 'FAIL'} | "
                     f"{(x['first_errors'] or [''])[0][:140]} |")
    for m in missing:
        lines.append(f"| required unit missing: `{m}` | FAIL | |")
    report = "\n".join(lines) + "\n"
    print(report)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(report)
    return 1 if result["required_failures"] else 0


if __name__ == "__main__":
    sys.exit(main())
