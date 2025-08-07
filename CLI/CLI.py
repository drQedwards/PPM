# ppm/cli.py
import argparse
import importlib
from ppm import core

def _scan_file(path):
    """Return list of top-level import specs found in a Python file."""
    import ast, pathlib
    txt = pathlib.Path(path).read_text()
    tree = ast.parse(txt)
    pkgs = {node.module.split('.')[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module}
    pkgs.update(alias.name.split('.')[0]
                for node in ast.walk(tree)
                if isinstance(node, ast.Import)
                for alias in node.names)
    return sorted(pkgs)

def import_cmd(pkgs, verbose=False):
    for spec in pkgs:
        core.import_package(spec, verbose=verbose)

def main(argv=None):
    p = argparse.ArgumentParser(prog="ppm")
    sub = p.add_subparsers(dest="cmd")
    ip = sub.add_parser("import", help="Import packages into PPM cache")
    ip.add_argument("spec", nargs="*", help="name or name==version")
    ip.add_argument("-f", "--from-file", metavar="script.py",
                    help="scan a Python file for imports")
    ip.add_argument("-v", "--verbose", action="store_true")
    ns = p.parse_args(argv)

    if ns.cmd == "import":
        pkgs = ns.spec
        if ns.from_file:
            pkgs.extend(_scan_file(ns.from_file))
        if not pkgs:
            p.error("nothing to import")
        import_cmd(pkgs, ns.verbose)
    else:
        p.print_help()

if __name__ == "__main__":
    main()
