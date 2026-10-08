"""Static checks for tools/ci/batch_build_check.py (the batch-build CI job).

The compile itself runs in .github/workflows/batch-build.yml; here we only make
sure the REQUIRED lists point at files that exist, so a rename cannot silently
drop a unit from the required set.
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("batch_build_check", ROOT / "tools" / "ci" / "batch_build_check.py")
bbc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bbc)


def test_required_units_exist():
    for rel in bbc.REQUIRED_C + bbc.REQUIRED_CXX + bbc.REQUIRED_PYX:
        assert (ROOT / rel).is_file(), rel


def test_required_link_sources_exist():
    for spec in bbc.REQUIRED_LINKS:
        for rel in spec["sources"]:
            assert (ROOT / rel).is_file(), (spec["name"], rel)


def test_required_makefiles_exist():
    for spec in bbc.REQUIRED_MAKE:
        assert (ROOT / spec["dir"] / "Makefile").is_file(), spec["dir"]


def test_no_unit_is_both_required_kinds():
    assert not set(bbc.REQUIRED_C) & set(bbc.REQUIRED_CXX)


def test_failed_command_keeps_a_diagnostic(tmp_path):
    import sys
    r = bbc._run([sys.executable, "-c", "print('make: *** [panda.so] boom'); raise SystemExit(3)"], tmp_path)
    assert r["ok"] is False and r["rc"] == 3
    assert r["first_errors"] and "boom" in r["first_errors"][-1]


def test_tracked_files_are_nul_split():
    files = bbc._tracked((".py",))
    assert "tools/ci/batch_build_check.py" in files
    assert all((ROOT / f).is_file() for f in files)
