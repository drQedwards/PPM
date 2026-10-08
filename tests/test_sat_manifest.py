"""Recompute the published SAT proof manifest root (hash-only; CI has no drat-trim).

See docs/SAT-PROOF-MANIFEST.md. This checks the published files only; it makes
no complexity claim. P versus NP is open.
"""

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUB = ROOT / "proofs" / "sat-manifest"
VERIFY = ROOT / "tools" / "sat_proof" / "verify_manifest.py"
EXPECTED_ROOT = "723cbe658e875821ac2fbb5cd8bfd6937f3a61a1aba7e6665aa6ae5e2c6e6078"


def _verify(path):
    return subprocess.run(
        [sys.executable, str(VERIFY), str(path), "--expect-root", EXPECTED_ROOT, "--hash-only"],
        capture_output=True, text=True,
    )


def test_published_manifest_recomputes_expected_root():
    r = _verify(PUB)
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"expected root {EXPECTED_ROOT} MATCH" in r.stdout
    assert "instances 427 problems 0" in r.stdout
    assert "RESULT: PASS" in r.stdout


def test_sha256sums_cover_every_published_file():
    listed = {}
    for line in (PUB / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split(None, 1)
        listed[name.lstrip("*").removeprefix("./")] = digest
    on_disk = {p.relative_to(PUB).as_posix() for p in PUB.rglob("*") if p.is_file()}
    assert on_disk - set(listed) == {"README.md", "SHA256SUMS"}
    for name, digest in listed.items():
        assert hashlib.sha256((PUB / name).read_bytes()).hexdigest() == digest, name


def test_harness_scripts_match_manifest_hashes():
    m = json.loads((PUB / "manifest.json").read_text())
    files = m["sources"]["harness"]["files"]
    assert files
    for f in files:
        data = (PUB / "harness" / f["path"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == f["sha256"], f["path"]


def test_tampered_instance_is_rejected(tmp_path):
    copy = tmp_path / "sat-manifest"
    shutil.copytree(PUB, copy)
    cnf = copy / "instances" / "f002-unsat-core.cnf"
    cnf.write_bytes(cnf.read_bytes() + b"c tampered\n")
    r = _verify(copy)
    assert r.returncode != 0
    assert "cnf hash mismatch f002-unsat-core" in r.stdout


def test_wrong_expected_root_is_rejected():
    r = subprocess.run(
        [sys.executable, str(VERIFY), str(PUB), "--expect-root", "00" * 32, "--hash-only"],
        capture_output=True, text=True,
    )
    assert r.returncode != 0
    assert "MISMATCH" in r.stdout
