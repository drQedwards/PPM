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
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import requests
from packaging.markers import Marker
from packaging.requirements import Requirement
from packaging.tags import Tag, sys_tags
from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import InvalidVersion, Version
import tomli_w

# =========================================================
# Constants
# =========================================================

DEFAULT_UA = "PPM-Resolver/2.1 (+https://github.com/drQedwards/PPM)"


# =========================================================
# Data structures
# =========================================================

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


# =========================================================
# Utilities
# =========================================================

def ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)

def sha256_file(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for part in iter(lambda: f.read(chunk), b""):
            h.update(part)
    return h.hexdigest()

def to_simple_project_url(index: str, project: str) -> str:
    proj = canonicalize_name(project).replace("_", "-")
    return urllib.parse.urljoin(index.rstrip("/") + "/", proj + "/")

def env_mapping() -> Dict[str, str]:
    py = sys.version_info
    impl = sys.implementation.name
    python_version = f"{py.major}.{py.minor}"
    return {
        "implementation_name": impl,
        "implementation_version": python_version,
        "os_name": os.name,
        "platform_machine": "",     # fill if desired: platform.machine()
        "platform_python_implementation": impl.capitalize(),
        "platform_release": "",
        "platform_system": "",
        "platform_version": "",
        "python_full_version": sys.version.split()[0],
        "python_version": python_version,
        "sys_platform": sys.platform,
        "extra": "",
    }

def marker_allows(marker: Optional[Marker]) -> bool:
    if marker is None:
        return True
    try:
        return bool(marker.evaluate(env_mapping()))
    except Exception:
        return False

def is_prerelease(v: Version) -> bool:
    return v.is_prerelease

def parse_artifact_hash_from_href(href: str) -> Optional[str]:
    # PEP 503 recommends fragments like #sha256=<hex>
    frag = urllib.parse.urlparse(href).fragment or ""
    m = re.search(r"(?:^|&)sha256=([0-9a-fA-F]{64})(?:&|$)", frag)
    return m.group(1).lower() if m else None

def request_session(timeout: int, retries: int, ua: str) -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = ua
    # Store simple settings on the session; we read them back explicitly.
    s.request_timeout = timeout          # type: ignore[attr-defined]
    s.request_retries = max(0, retries)  # type: ignore[attr-defined]
    return s

def http_get_text(session: requests.Session, url: str) -> str:
    tmo = getattr(session, "request_timeout", 60)
    tries = getattr(session, "request_retries", 2)
    for i in range(tries + 1):
        try:
            r = session.get(url, timeout=tmo)
            r.raise_for_status()
            return r.text
        except Exception:
            if i == tries:
                raise

def fetch_simple_listing(session: requests.Session, url: str) -> List[Tuple[str, str]]:
    # Return list of (href, filename)
    text = http_get_text(session, url)
    out: List[Tuple[str, str]] = []
    # Minimal regex extraction is sufficient for PEP 503 Simple pages.
    for m in re.finditer(r'href=[\'"]([^\'"]+)[\'"][^>]*>([^<]+)', text, re.IGNORECASE):
        href = m.group(1)
        name = m.group(2).strip()
        out.append((urllib.parse.urljoin(url, href), name))
    return out

def best_record_tag(tags: List[Tag], env_order: List[Tag]) -> Tuple[str|None, str|None, str|None]:
    # Choose the first environment tag that exists in the wheel's tag set
    for t in env_order:
        if t in tags:
            return t.interpreter, t.abi, t.platform
    return None, None, None

def pick_artifact(cands: List[Artifact], env_order: List[Tag]) -> Optional[Artifact]:
    # Prefer wheels by env tag order; then sdists
    wheels = [c for c in cands if c.is_wheel]
    order = {str(t): i for i, t in enumerate(env_order)}
    def score(a: Artifact) -> int:
        if not a.py_tag:
            return 9_000_000
        return order.get(f"{a.py_tag}-{a.abi_tag}-{a.plat_tag}", 8_000_000)
    wheels.sort(key=score)
    if wheels:
        return wheels[0]
    sdists = [c for c in cands if not c.is_wheel]
    return sdists[0] if sdists else None

def preferred_versions(req: Requirement, versions: List[Version]) -> List[Version]:
    """Prefer stable versions unless prereleases are explicitly requested or no stable exists."""
    if not versions:
        return []
    # Filter per specifier first (respecting prerelease semantics).
    def ok(v: Version) -> bool:
        return (not req.specifier) or req.specifier.contains(v, prereleases=None)
    viable = [v for v in versions if ok(v)]
    if not viable:
        return []
    has_stable = any(not v.is_prerelease for v in viable)
    pre_explicit = (req.specifier is not None and req.specifier.prereleases is True)
    if pre_explicit or not has_stable:
        return sorted(viable)
    return sorted([v for v in viable if not v.is_prerelease])

def parse_requires_from_wheel(path: str) -> List[str]:
    reqs: List[str] = []
    try:
        with zipfile.ZipFile(path) as zf:
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

def deduce_platform_label(primary: str, extras: Sequence[str]) -> str:
    s = " ".join([primary, *extras]).lower()
    if "cu118" in s: return "cu118"
    if "cu126" in s: return "cu126"
    if "cu128" in s: return "cu128"
    if "rocm6.3" in s or "rocm63" in s: return "rocm63"
    return "cpu"

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

def write_matrix_inputs(root: str, pkgs: List[PackageLock]) -> None:
    p = os.path.join(root, ".ppm", "matrix_inputs.txt")
    with open(p, "w", encoding="utf-8") as f:
        for pkl in pkgs:
            for a in pkl.artifacts:
                if a.sha256:
                    f.write(f"{a.filename}\t{a.sha256}\n")

def write_matrix_plan(root: str, platform_label: str) -> None:
    p = os.path.join(root, ".ppm", "matrix_plan.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"platform": platform_label}, f, indent=2)

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
        print("[ok] lock verified for this environment]")
    return 0 if ok else 2

if __name__ == "__main__":
    sys.exit(verify(os.getcwd()))
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(body))


# =========================================================
# Resolution core
# =========================================================

class Resolver:
    def __init__(self,
                 root: str,
                 index_url: str,
                 extra_indexes: Sequence[str],
                 timeout: int,
                 retries: int,
                 user_agent: str,
                 strict_hash: bool,
                 follow_transitives: bool) -> None:
        self.root = os.path.abspath(root)
        self.index_url = index_url
        self.extra_indexes = list(extra_indexes)
        self.timeout = timeout
        self.retries = retries
        self.user_agent = user_agent
        self.strict_hash = strict_hash
        self.follow_transitives = follow_transitives

        self.cache_dir = os.path.join(self.root, ".ppm", "cache")
        ensure_dir(self.cache_dir)
        ensure_dir(os.path.join(self.root, ".ppm"))

        self.session = request_session(timeout, retries, user_agent)
        self.env_tags = list(sys_tags())  # ordered best-first

        self.resolved: Dict[str, PackageLock] = {}
        self.seen: Dict[str, bool] = {}

    def _search_urls(self, project: str) -> List[str]:
        urls = [to_simple_project_url(self.index_url, project)]
        for e in self.extra_indexes:
            urls.append(to_simple_project_url(e, project))
        return urls

    def _download(self, url: str) -> Tuple[str, str]:
        tmo = getattr(self.session, "request_timeout", 60)
        tries = getattr(self.session, "request_retries", 2)
        fname = os.path.basename(urllib.parse.urlparse(url).path)
        local = os.path.join(self.cache_dir, fname)

        if os.path.exists(local):
            return local, sha256_file(local)

        for i in range(tries + 1):
            try:
                with self.session.get(url, stream=True, timeout=tmo) as r:
                    r.raise_for_status()
                    with open(local, "wb") as f:
                        for chunk in r.iter_content(1 << 20):
                            if chunk:
                                f.write(chunk)
                return local, sha256_file(local)
            except Exception:
                if i == tries:
                    raise
        raise RuntimeError("unreachable")

    def _gather_candidates(self, req: Requirement) -> Tuple[List[Artifact], List[Version]]:
        candidates: List[Artifact] = []
        versions: List[Version] = []

        for s_url in self._search_urls(req.name):
            try:
                listing = fetch_simple_listing(self.session, s_url)
            except Exception:
                continue

            for href, filename in listing:
                lower = filename.lower()
                if lower.endswith(".whl"):
                    try:
                        _proj, ver, build, tags = parse_wheel_filename(filename)
                    except Exception:
                        continue
                    ver_s = str(ver)
                    try:
                        vv = Version(ver_s)
                    except InvalidVersion:
                        continue
                    py_tag, abi_tag, plat_tag = best_record_tag(list(tags), self.env_tags)
                    h = parse_artifact_hash_from_href(href) or ""
                    candidates.append(Artifact(
                        filename=filename, url=href, sha256=h,
                        version=ver_s, py_tag=py_tag, abi_tag=abi_tag, plat_tag=plat_tag,
                        is_wheel=True
                    ))
                    versions.append(vv)
                elif lower.endswith((".tar.gz", ".zip", ".tar.bz2", ".tar.xz")):
                    # Basic sdist version parse
                    ver_guess = None
                    m = re.match(rf"^{re.escape(req.name)}-(.+)\.(tar\.gz|zip|tar\.bz2|tar\.xz)$",
                                 filename, re.IGNORECASE)
                    if m:
                        ver_guess = m.group(1)
                    if not ver_guess:
                        parts = filename.split("-")
                        if len(parts) >= 2:
                            ver_guess = parts[1].split(".tar")[0].split(".zip")[0]
                    if not ver_guess:
                        continue
                    try:
                        vv = Version(ver_guess)
                    except InvalidVersion:
                        continue
                    h = parse_artifact_hash_from_href(href) or ""
                    candidates.append(Artifact(
                        filename=filename, url=href, sha256=h,
                        version=str(vv), py_tag=None, abi_tag=None, plat_tag=None,
                        is_wheel=False
                    ))
                    versions.append(vv)

        return candidates, versions

    def _resolve_one(self, req: Requirement) -> PackageLock:
        name_norm = canonicalize_name(req.name)
        if name_norm in self.resolved:
            return self.resolved[name_norm]
        if name_norm in self.seen:
            raise SystemExit(f"cyclic or repeated requirement detected: {req}")
        self.seen[name_norm] = True

        candidates, versions = self._gather_candidates(req)
        if not candidates:
            raise SystemExit(f"No candidates found for {req!s}")

        versions = preferred_versions(req, versions)
        if not versions:
            raise SystemExit(f"No versions satisfy specifier: {req!s}")

        best_v = versions[-1]
        cands = [c for c in candidates if Version(c.version) == best_v]

        chosen = pick_artifact(cands, self.env_tags)
        if not chosen:
            raise SystemExit(f"No compatible artifact for {req!s} at {best_v} (candidates={len(cands)})")

        local, digest = self._download(chosen.url)
        chosen.sha256 = chosen.sha256 or digest

        if self.strict_hash and not chosen.sha256:
            raise SystemExit(f"Strict hash enabled: {chosen.filename} lacks sha256")

        pkl = PackageLock(
            name=name_norm,
            version=chosen.version,
            markers=str(req.marker) if req.marker else None,
            artifacts=[chosen],
        )
        self.resolved[name_norm] = pkl

        # Transitives (wheel-only MVP)
        if self.follow_transitives and chosen.is_wheel and marker_allows(req.marker):
            for spec in parse_requires_from_wheel(local):
                try:
                    r = Requirement(spec)
                except Exception:
                    continue
                if not marker_allows(r.marker):
                    continue
                cn = canonicalize_name(r.name)
                if cn not in self.resolved:
                    self._resolve_one(r)

        return pkl

    def resolve_all(self, requirements: Iterable[str]) -> List[PackageLock]:
        for rtxt in requirements:
            r = Requirement(rtxt)
            if marker_allows(r.marker):
                self._resolve_one(r)
        # Deterministic package order
        return [self.resolved[k] for k in sorted(self.resolved.keys())]


# =========================================================
# CLI
# =========================================================

def main() -> int:
    ap = argparse.ArgumentParser(description="Resolve packages and emit lock artifacts.")
    ap.add_argument("--root", required=True, help="project root")
    ap.add_argument("--index", required=True, help="primary Simple index (PEP 503)")
    ap.add_argument("--extra-index", action="append", default=[], help="additional Simple index (repeatable)")
    ap.add_argument("--timeout", type=int, default=60, help="HTTP timeout seconds (default: 60)")
    ap.add_argument("--retries", type=int, default=2, help="HTTP retries per request (default: 2)")
    ap.add_argument("--ua", default=DEFAULT_UA, help="HTTP User-Agent string")
    ap.add_argument("--no-transitives", action="store_true", help="Do not traverse Requires-Dist transitives")
    ap.add_argument("--strict-hash", action="store_true", help="Fail if any chosen artifact lacks SHA-256")
    ap.add_argument("requirements", nargs="+", help="PEP 508 requirement strings")
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    ensure_dir(os.path.join(root, ".ppm"))

    resolver = Resolver(
        root=root,
        index_url=args.index,
        extra_indexes=args.extra_index,
        timeout=args.timeout,
        retries=args.retries,
        user_agent=args.ua,
        strict_hash=args.strict_hash,
        follow_transitives=not args.no_transitives,
    )

    pkgs = resolver.resolve_all(args.requirements)

    # Sort artifacts deterministically: wheel first, then filename
    for p in pkgs:
        p.artifacts.sort(key=lambda a: (not a.is_wheel, a.filename))

    write_lock_json(os.path.join(root, ".ppm", "lock.json"), pkgs, {
        "primary": args.index,
        "extra": args.extra_index,  # list of extras
    })
    write_pylock_toml(os.path.join(root, "pylock.toml"), pkgs)
    write_verifier(os.path.join(root, "resolver.py"), pkgs)

    platform_label = deduce_platform_label(args.index, args.extra_index)
    write_matrix_inputs(root, pkgs)
    write_matrix_plan(root, platform_label)

    print("[ok] wrote .ppm/lock.json")
    print("[ok] wrote pylock.toml")
    print("[ok] wrote resolver.py")
    print("[ok] wrote .ppm/matrix_inputs.txt")
    print("[ok] wrote .ppm/matrix_plan.json")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
