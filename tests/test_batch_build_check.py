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
