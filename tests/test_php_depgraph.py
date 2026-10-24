import json, shutil, subprocess
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "php_depgraph"


@pytest.mark.skipif(shutil.which("php") is None, reason="php not installed")
def test_php_depgraph_fixture(tmp_path):
    units, graph = tmp_path / "u.json", tmp_path / "g.json"
    subprocess.run(["php", str(ROOT / "tools/build_memory/php_depgraph.php"), str(FIX),
                    "--out", str(units), "--graph", str(graph)], check=True)
    u = {x["path"]: x for x in json.loads(units.read_text())["units"]}
    assert u["index.php"]["depends_on_units"] == ["src/Bag.php"]
    assert all(x["ok"] for x in u.values())
    g = json.loads(graph.read_text())
    labels = {n["label"] for n in g["nodes"]}
    assert "php:iter:Demo\\Bag" in labels
    assert "php:iter:Demo\\Bag::getIterator" in labels
    assert g["meta"]["root_entry"] == "index.php"
