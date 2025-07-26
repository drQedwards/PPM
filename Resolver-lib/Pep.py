#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import hashlib
from dataclasses import dataclass, asdict
from typing import List, Optional, Tuple, Dict

try:
    from nacl.signing import SigningKey, VerifyKey
    from nacl.exceptions import BadSignatureError
except Exception as e:
    print("PyNaCl is required: pip install pynacl", file=sys.stderr)
    raise

# --------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------

def b64e(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")

def b64d(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"))

def sha256_file(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for part in iter(lambda: f.read(chunk), b""):
            h.update(part)
    return h.hexdigest()

def ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)

def now_rfc3339() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

# --------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------

@dataclass
class SigItem:
    filename: str
    sha256: str
    pubkey: str   # base64(32)
    sig: str      # base64(64)

@dataclass
class SignaturesDoc:
    mode: str              # "raw" or "ph"
    items: List[SigItem]

    def to_json(self) -> str:
        return json.dumps({
            "mode": self.mode,
            "items": [asdict(i) for i in self.items],
        }, indent=2)

    @staticmethod
    def from_json(text: str) -> "SignaturesDoc":
        obj = json.loads(text)
        items = [SigItem(**x) for x in obj.get("items", [])]
        return SignaturesDoc(mode=obj.get("mode", "raw"), items=items)

# --------------------------------------------------------------------
# Key management
# --------------------------------------------------------------------

def keygen(out_priv: str, out_pub: str) -> None:
    sk = SigningKey.generate()
    vk = sk.verify_key
    ensure_dir(os.path.dirname(os.path.abspath(out_priv)) or ".")
    ensure_dir(os.path.dirname(os.path.abspath(out_pub)) or ".")
    with open(out_priv, "w", encoding="utf-8") as f:
        f.write(b64e(bytes(sk)))
    with open(out_pub, "w", encoding="utf-8") as f:
        f.write(b64e(bytes(vk)))
    print(f"[ok] wrote {out_priv}")
    print(f"[ok] wrote {out_pub}")

def load_privkey(path: str) -> SigningKey:
    data = b64d(open(path, "r", encoding="utf-8").read().strip())
    return SigningKey(data)

def load_pubkey(path: str) -> VerifyKey:
    data = b64d(open(path, "r", encoding="utf-8").read().strip())
    return VerifyKey(data)

# --------------------------------------------------------------------
# Artifact selection
# --------------------------------------------------------------------

def load_matrix_inputs(path: str) -> List[Tuple[str, str]]:
    """
    matrix_inputs.txt: TSV "filename<TAB>sha256"
    """
    items: List[Tuple[str, str]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) != 2:
                continue
            items.append((parts[0], parts[1].lower()))
    return items

def collect_from_cache(cache_dir: str, filenames: List[str]) -> List[Tuple[str, str]]:
    """
    Given filenames, compute sha256 for each in cache_dir.
    Returns (filename, sha256hex).
    """
    out: List[Tuple[str, str]] = []
    for fn in filenames:
        full = os.path.join(cache_dir, fn)
        if not os.path.exists(full):
            raise SystemExit(f"missing artifact in cache: {full}")
        out.append((fn, sha256_file(full)))
    return out

# --------------------------------------------------------------------
# Signing / verification
# --------------------------------------------------------------------

def sign_artifacts(root: str,
                   mode: str,
                   private_key_path: str,
                   out_signatures: str,
                   filenames: Optional[List[str]] = None,
                   from_matrix_inputs: bool = True) -> None:
    """
    Sign artifacts under <root>/.ppm/cache.
    If filenames is None and from_matrix_inputs=True, read the list from matrix_inputs.txt.
    """
    cache = os.path.join(root, ".ppm", "cache")
    ensure_dir(os.path.join(root, ".ppm"))

    if filenames:
        pairs = collect_from_cache(cache, filenames)
    else:
        if not from_matrix_inputs:
            raise SystemExit("No filenames provided and --from-matrix-inputs disabled.")
        matrix_path = os.path.join(root, ".ppm", "matrix_inputs.txt")
        pairs = load_matrix_inputs(matrix_path)

    sk = load_privkey(private_key_path)
    vk = sk.verify_key
    vk_b64 = b64e(bytes(vk))

    items: List[SigItem] = []
    for fn, sha in pairs:
        full = os.path.join(cache, fn)
        with open(full, "rb") as f:
            data = f.read()

        if mode in ("ph", "ed25519ph"):
            # Ed25519ph = prehash with SHA-512
            h = hashlib.sha512(data).digest()
            sig = sk.sign(h, encoder=None).signature  # sign prehash bytes
        else:
            # raw: sign the entire message
            sig = sk.sign(data, encoder=None).signature

        items.append(SigItem(filename=fn, sha256=sha, pubkey=vk_b64, sig=b64e(sig)))

    doc = SignaturesDoc(mode=("ph" if mode == "ed25519ph" else mode), items=items)
    with open(out_signatures, "w", encoding="utf-8") as f:
        f.write(doc.to_json())
    print(f"[ok] wrote {out_signatures} ({len(items)} items)")

def verify_signatures(root: str,
                      signatures_path: str,
                      default_pubkey: Optional[str] = None) -> Tuple[int, int]:
    """
    Verify signatures.json against artifacts in cache.
    Returns (invalid_sig_count, hash_mismatch_count).
    """
    cache = os.path.join(root, ".ppm", "cache")
    doc = SignaturesDoc.from_json(open(signatures_path, "r", encoding="utf-8").read())
    mode = doc.mode.lower()
    use_ph = mode in ("ph", "ed25519ph")

    default_vk: Optional[VerifyKey] = None
    if default_pubkey:
        default_vk = load_pubkey(default_pubkey)

    invalid = 0
    mismatch = 0

    for it in doc.items:
        full = os.path.join(cache, it.filename)
        if not os.path.exists(full):
            print(f"[!] missing artifact: {it.filename}")
            mismatch += 1
            continue

        actual = sha256_file(full)
        if it.sha256 and actual.lower() != it.sha256.lower():
            print(f"[!] hash mismatch: {it.filename}  got={actual}  expected={it.sha256}")
            mismatch += 1

        try:
            vk = VerifyKey(b64d(it.pubkey)) if it.pubkey else default_vk
            if vk is None:
                print(f"[!] no pubkey for {it.filename}")
                invalid += 1
                continue

            sig = b64d(it.sig)
            data = open(full, "rb").read()
            if use_ph:
                h = hashlib.sha512(data).digest()
                vk.verify(h, sig)
            else:
                vk.verify(data, sig)
        except BadSignatureError:
            print(f"[!] invalid signature: {it.filename}")
            invalid += 1

    return invalid, mismatch

def write_provenance(root: str,
                     signatures_path: str,
                     out_path: str,
                     builder_id: str = "ppm-resolver",
                     predicate_type: str = "https://slsa.dev/provenance/v1") -> None:
    """
    Minimal in-toto/SLSA-like statement with subjects (sha256) and signing mode.
    """
    doc = SignaturesDoc.from_json(open(signatures_path, "r", encoding="utf-8").read())
    subjects = []
    for it in doc.items:
        subjects.append({
            "name": it.filename,
            "digest": {"sha256": it.sha256},
        })

    statement = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": subjects,
        "predicateType": predicate_type,
        "predicate": {
            "builder": {"id": builder_id},
            "metadata": {
                "buildStartedOn": now_rfc3339(),
                "buildFinishedOn": now_rfc3339(),
            },
            "buildType": "ppm/resolve+sign",
            "invocation": {
                "configSource": {"uri": ""},
                "parameters": {
                    "mode": doc.mode,
                },
                "environment": {
                    "root": os.path.abspath(root),
                    "python": sys.version.split()[0],
                    "platform": sys.platform,
                },
            },
        },
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(statement, f, indent=2)
    print(f"[ok] wrote {out_path}")

# --------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(prog="pep", description="PEP signing & verification tools for PPM.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("keygen", help="Generate Ed25519 keypair (base64).")
    sp.add_argument("--out-priv", default="ed25519.priv")
    sp.add_argument("--out-pub",  default="ed25519.pub")

    sp = sub.add_parser("sign", help="Sign artifacts in cache and emit signatures.json.")
    sp.add_argument("--root", required=True)
    sp.add_argument("--mode", choices=["raw", "ph", "ed25519ph"], default="raw",
                    help="raw = sign full bytes; ph/ed25519ph = prehash with SHA-512")
    sp.add_argument("--key", required=True, help="path to base64 private key")
    sp.add_argument("--out", default=None, help="output signatures.json (default: <root>/.ppm/signatures.json)")
    sp.add_argument("--no-matrix-inputs", action="store_true",
                    help="do not read matrix_inputs.txt; sign only the provided filenames")
    sp.add_argument("filenames", nargs="*", help="explicit file names to sign (under .ppm/cache/)")

    sp = sub.add_parser("verify", help="Verify signatures.json against cache artifacts.")
    sp.add_argument("--root", required=True)
    sp.add_argument("--signatures", default=None,
                    help="path to signatures.json (default: <root>/.ppm/signatures.json)")
    sp.add_argument("--pubkey", default=None,
                    help="optional default pubkey base64 file; used if items omit pubkey")
    sp.add_argument("--report", default=None,
                    help="optional write JSON report to this path")

    sp = sub.add_parser("provenance", help="Emit minimal in-toto/SLSA statement.")
    sp.add_argument("--root", required=True)
    sp.add_argument("--signatures", default=None)
    sp.add_argument("--out", default=None)

    args = ap.parse_args()

    if args.cmd == "keygen":
        keygen(args.out_priv, args.out_pub)
        return 0

    if args.cmd == "sign":
        root = os.path.abspath(args.root)
        out = args.out or os.path.join(root, ".ppm", "signatures.json")
        from_matrix = (not args.no_matrix_input s)
        sign_artifacts(root, args.mode, args.key, out,
                       filenames=args.filenames if args.filenames else None,
                       from_matrix_inputs=from_matrix)
        return 0

    if args.cmd == "verify":
        root = os.path.abspath(args.root)
        sigp = args.signatures or os.path.join(root, ".ppm", "signatures.json")
        invalid, mismatch = verify_signatures(root, sigp, args.pubkey)
        report = args.report
        if report:
            with open(report, "w", encoding="utf-8") as f:
                json.dump({
                    "invalid_signatures": invalid,
                    "hash_mismatches": mismatch,
                }, f, indent=2)
            print(f"[ok] wrote {report}")
        status = 0 if (invalid == 0 and mismatch == 0) else 2
        print(f"[summary] invalid_signatures={invalid} hash_mismatches={mismatch}")
        return status

    if args.cmd == "provenance":
        root = os.path.abspath(args.root)
        sigp = args.signatures or os.path.join(root, ".ppm", "signatures.json")
        out = args.out or os.path.join(root, ".ppm", "provenance.json")
        write_provenance(root, sigp, out)
        return 0

    return 1

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
