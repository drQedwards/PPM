#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import textwrap
import urllib.parse
import zipfile
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple

import requests
from packaging.requirements import Requirement
from packaging.version import Version, InvalidVersion
from packaging.tags import sys_tags, Tag
from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.markers import Marker
import tomli_w

# ---- PEP references (see docs):
# PEP 503: Simple index + normalized names
# PEP 440: Versions/specifiers
# PEP 508: Environment markers
# PEP 425: Compatibility tags; packaging.tags provides ordered env tags
# Docs: packaging.tags.sys_tags is ordered best-first

@dataclass
class Artifact:
    filename: str
    url: str
    sha256: str
    version: str
    py_tag: str | None
    abi_tag: str | None
    plat_tag: str | None
    is_wheel: bool

@dataclass
class PackageLock:
    name: str       # normalized
    version: str
    markers: str | None
    artifacts: List[Artifact]

def ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)

def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for ch in iter(lambda: f.read(1 << 20), b""):
            h.update(ch)
    return h.hexdigest()

def simple_project_url(index: str, project: str) -> str:
    proj = canonicalize_name(project).replace("_", "-")
    return urllib.parse.urljoin(index.rstrip("/") + "/", proj + "/")

def fetch_simple_listing(url: str) -> List[Tuple[str, str]]:
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    hrefs: List[Tuple[str, str]] = []
    for m in re.finditer(r'href=[\'"]([^\'"]+)[\'"][^>]*>([^<]+)', r.text, re.I):
        href = m.group(1)
        text = m.group(2)
        hrefs.append((urllib.parse.urljoin(url, href), text.strip()))
    return hrefs

def best_tag_for_record(tags: List[Tag], env_order: List[Tag]) -> Tuple[str|None,str|None,str|None]:
    env_set = list(env_order)
    for t in env_set:
        if t in tags:
            return t.interpreter, t.abi, t.platform
    return None, None, None

def pick_artifact(cands: List[Artifact], env_order: List[Tag]) -> Optional[Artifact]:
    wheels = [c for c in cands if c.is_wheel]
    order = {str(t): i for i, t in enumerate(env_order)}
    def score(a: Artifact) -> int:
        if not a.py_tag:  # unknown tag => worse
            return 9_000_000
        return order.get(f"{a.py_tag}-{a.abi_tag}-{a.plat_tag}", 8_000_000)
    wheels.sort(key=score)
    if wheels:
        return wheels[0]
    sdists = [c for c in cands if not c.is_wheel]
    return sdists[0] if sdists else None

def download(url: str, dest: str) -> Tuple[str, str]:
    ensure_dir(dest)
    filename = os.path.basename(urllib.parse.urlparse(url).path)
    local = os.path.join(dest, filename)
    with requests.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(local, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                if chunk:
                    f.write(chunk)
    return local, sha256_file(local)

def parse_requires_from_wheel(wheel_path: str) -> List[str]:
    reqs: List[str] = []
    try:
        with zipfile.ZipFile(wheel_path) as zf:
            meta_name = None
            for n in zf.namelist():
                if n.endswith(".dist-info/METADATA"):
                    meta_name = n
                    break
            if not meta_name:
                return reqs
            with zf.open(meta_name) as fp:
                for raw in fp.read().decode("utf-8", errors="replace").splitlines():
                    if raw.startswith("Requires-Dist: "):
                        reqs.append(raw[len("Requires-Dist: "):].strip())
    except Exception:
        pass
    return reqs

def env_mapping() -> Dict[str, str]:
    # Minimal environment for PEP 508 marker evaluation.
    py = sys.version_info
    plat = sys.platform
    impl = sys.implementation.name
    python_version = f"{py.major}.{py.minor}"
    return {
        "implementation_name": impl,
        "implementation_version": python_version,
        "os_name": os.name,
        "platform_machine": "",     # could fill with platform.machine()
        "platform_python_implementation": impl.capitalize(),
        "platform_release": "",     # platform.release()
        "platform_system": "",      # platform.system()
        "platform_version": "",     # platform.version()
        "python_full_version": sys.version.split()[0],
        "python_version": python_version,
        "sys_platform": plat,
        "extra": "",
    }

def marker_allows(marker: Optional[Marker]) -> bool:
    if marker is None:
        return True
    try:
        return bool(marker.evaluate(env_mapping()))
    except Exception:
        return False

def resolve(requirements: List[str],
            index_url: str,
            extra_index_url: Optional[str],
            root: str,
            follow_transitives: bool) -> List[PackageLock]:

    env_tags = list(sys_tags())  # ordered best-first
    cache_dir = os.path.join(root, ".ppm", "cache")
    ensure_dir(cache_dir)

    resolved: Dict[str, PackageLock] = {}
    seen: Dict[str, bool] = {}

    queue: List[Requirement] = [Requirement(r) for r in requirements]

    while queue:
        req = queue.pop(0)
        name_norm = canonicalize_name(req.name)
        if name_norm in resolved:
            # Already pinned; (optionally check spec compatibility)
            continue
        if name_norm in seen:
            continue
        seen[name_norm] = True

        search_urls = [simple_project_url(index_url, req.name)]
        if extra_index_url:
            search_urls.append(simple_project_url(extra_index_url, req.name))

        candidates: List[Artifact] = []
        chosen_version: Optional[Version] = None

        for s_url in search_urls:
            try:
                hrefs = fetch_simple_listing(s_url)
            except Exception:
                continue
            for href, filename in hrefs:
                fn_lower = filename.lower()
                # Wheel
                if fn_lower.endswith(".whl"):
                    try:
                        _proj, ver, build, tags = parse_wheel_filename(filename)
                    except Exception:
                        continue
                    ver_s = str(ver)
                    try:
                        ver_v = Version(ver_s)
                    except InvalidVersion:
                        continue
                    if req.specifier and not req.specifier.contains(ver_v, prereleases=True):
                        continue
                    py_tag = abi_tag = plat_tag = None
                    py_tag, abi_tag, plat_tag = best_tag_for_record(list(tags), env_tags)
                    candidates.append(Artifact(
                        filename=filename, url=href, sha256="",
                        version=ver_s, py_tag=py_tag, abi_tag=abi_tag, plat_tag=plat_tag,
                        is_wheel=True
                    ))
                    if chosen_version is None or ver_v > chosen_version:
                        chosen_version = ver_v
                # sdist
                elif any(fn_lower.endswith(ext) for ext in (".tar.gz", ".zip", ".tar.bz2", ".tar.xz")):
                    # naive version pull
                    ver_guess = None
                    m = re.match(rf"^{re.escape(req.name)}-(.+)\.(tar\.gz|zip|tar\.bz2|tar\.xz)$",
                                 filename, re.I)
                    if m:
                        ver_guess = m.group(1)
                    if ver_guess:
                        try:
                            ver_v = Version(ver_guess)
                        except InvalidVersion:
                            continue
                        if req.specifier and not req.specifier.contains(ver_v, prereleases=True):
                            continue
                        candidates.append(Artifact(
                            filename=filename, url=href, sha256="",
                            version=str(ver_v),
                            py_tag=None, abi_tag=None, plat_tag=None, is_wheel=False
                        ))
                        if chosen_version is None or ver_v > chosen_version:
                            chosen_version = ver_v

        if not candidates:
            raise SystemExit(f"No candidates found for {req!s}")

        if chosen_version:
            candidates = [c for c in candidates if Version(c.version) == chosen_version]

        chosen = pick_artifact(candidates, env_tags)
        if not chosen:
            raise SystemExit(f"No compatible artifact for {req!s} (candidates={len(candidates)})")

        local, digest = download(chosen.url, cache_dir)
        chosen.sha256 = digest

        lock_entry = PackageLock(
            name=name_norm,
            version=chosen.version,
            markers=str(req.marker) if req.marker else None,
            artifacts=[chosen],
        )
        resolved[name_norm] = lock_entry

        # Transitives (wheel only for MVP)
        if follow_transitives and chosen.is_wheel and marker_allows(req.marker):
            for line in parse_requires_from_wheel(local):
                try:
                    r = Requirement(line)
                except Exception:
                    continue
                if not marker_allows(r.marker):
                    continue
                cname = canonicalize_name(r.name)
                if cname not in resolved:
                    queue.append(r)

    return [resolved[k] for k in sorted(resolved.keys())]

def write_lock_json(path: str, pkgs: List[PackageLock], indexes: dict) -> None:
    out = {
        "version": 1,
        "indexes": indexes,
        "packages": [
            {
                "name": p.name,
                "version": p.version,
                "markers": p.markers,
                "artifacts": [asdict(a) for a in p.artifacts],
            } for p in pkgs
        ],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

def write_pylock_toml(path: str, pkgs: List[PackageLock]) -> None:
    doc = {
        "lock": {"version": "1.0"},
        "environment": {"python": sys.version.split()[0]},
        "packages": [],
    }
    for p in pkgs:
        entry = {
            "name": p.name,
            "version": p.version,
            "source": {"type": "pypi"},
            "artifacts": [a.filename for a in p.artifacts],
            "hashes": [f"sha256:{a.sha256}" for a in p.artifacts if a.sha256],
            "markers": p.markers or "",
        }
        doc["packages"].append(entry)
    with open(path, "wb") as f:
        f.write(tomli_w.dumps(doc).encode("utf-8"))

def write_verifier(path: str, pkgs: List[PackageLock]) -> None:
    lock = {
        "packages": [
            {
                "name": p.name,
                "version": p.version,
                "artifacts": [asdict(a) for a in p.artifacts],
            } for p in pkgs
        ]
    }
    body = f"""\
# Auto-generated by importresolver.py
from __future__ import annotations
import json, hashlib, sys, os
from packaging.tags import sys_tags

LOCK = {json.dumps(lock, indent=2)}

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for ch in iter(lambda: f.read(1<<20), b""):
            h.update(ch)
    return h.hexdigest()

def verify(root="."):
    tags = {{str(t) for t in sys_tags()}}
    ok = True
    for p in LOCK["packages"]:
        for a in p["artifacts"]:
            py = a.get("py_tag"); abi = a.get("abi_tag"); pl = a.get("plat_tag")
            if py and abi and pl:
                tag = f"{{py}}-{{abi}}-{{pl}}"
                if tag not in tags:
                    print(f"[!] incompatible tag for {{p['name']}}: {{tag}}")
                    ok = False
            sha = a.get("sha256")
            if sha:
                cache = os.path.join(root, ".ppm", "cache", a["filename"])
                if os.path.exists(cache):
                    got = sha256_file(cache)
                    if got != sha:
                        print(f"[!] hash mismatch for {{a['filename']}}: {{got}} != {{sha}}")
                        ok = False
                else:
                    print(f"[-] missing cache: {{cache}}")
    if ok:
        print("[ok] lock verified for this environment")
    return 0 if ok else 2

if __name__ == "__main__":
    sys.exit(verify(os.getcwd()))
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(body))

def main():
    ap = argparse.ArgumentParser(description="Resolve packages and emit lock artifacts.")
    ap.add_argument("--root", required=True)
    ap.add_argument("--index", required=True)
    ap.add_argument("--extra-index", default=None)
    ap.add_argument("--no-transitives", action="store_true",
                    help="Do not follow Requires-Dist from chosen wheels")
    ap.add_argument("requirements", nargs="+")
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    ensure_dir(os.path.join(root, ".ppm"))

    pkgs = resolve(
        requirements=args.requirements,
        index_url=args.index,
        extra_index_url=args.extra_index,
        root=root,
        follow_transitives=not args.no_transitives,
    )

    write_lock_json(os.path.join(root, ".ppm", "lock.json"), pkgs, {
        "primary": args.index,
        "extra": args.extra_index or "",
    })
    write_pylock_toml(os.path.join(root, "pylock.toml"), pkgs)
    write_verifier(os.path.join(root, "resolver.py"), pkgs)

    print("[ok] wrote .ppm/lock.json")
    print("[ok] wrote pylock.toml")
    print("[ok] wrote resolver.py")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
