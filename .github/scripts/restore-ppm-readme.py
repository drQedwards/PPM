#!/usr/bin/env python3
"""Restore PPM README from the adc8210 original and add live Stellar IDs."""
from pathlib import Path

p = Path("README.md")
t = p.read_text()
if t.startswith("# PLACEHOLDER") or len(t) < 1000:
    raise SystemExit(f"restored README too small: {len(t)} bytes")

needle = (
    "[![Sponsor](https://img.shields.io/badge/sponsor-DrQedwards-ea4aaa"
    "?logo=github-sponsors)](https://github.com/sponsors/DrQedwards)\n"
)
insert = needle + (
    "\nLive Stellar `pmll-anchor` IDs (mainnet + testnet): "
    "[docs/STELLAR.md](docs/STELLAR.md).\n"
)
if needle not in t:
    raise SystemExit("sponsor badge not found")
if "docs/STELLAR.md" not in t.split("Table of Contents")[0]:
    t = t.replace(needle, insert, 1)

toc_old = (
    "8. [Architecture](#-architecture)\n"
    "9. [Release Notes](#-release-notes)\n"
    "10. [Roadmap](#-roadmap)\n"
    "11. [Contributing & Sponsors](#-contributing--sponsors)\n"
)
toc_new = (
    "8. [Stellar commitments](#-stellar-commitments-pmll-anchor)\n"
    "9. [Architecture](#-architecture)\n"
    "10. [Release Notes](#-release-notes)\n"
    "11. [Roadmap](#-roadmap)\n"
    "12. [Contributing & Sponsors](#-contributing--sponsors)\n"
)
if toc_old not in t:
    raise SystemExit("toc block not found")
t = t.replace(toc_old, toc_new, 1)

section = """## ⚓ Stellar commitments (`pmll-anchor`)

Memory payloads stay **off-chain**. Optional 32-byte SHA-256 commitments are **live on Stellar mainnet** via [`drQedwards/pmll`](https://github.com/drQedwards/pmll) (`pmll-anchor`). Full payloads are never stored on-chain.

| Network | Contract ID | Explorer |
|---------|-------------|---------| 
| **mainnet** | `CCF3B64AXLS4OLY5RN4H4K2CFZAYNZCJQY5MKCKCVAKMZNH7G7F7XUUF` | [stellar.expert](https://stellar.expert/explorer/public/contract/CCF3B64AXLS4OLY5RN4H4K2CFZAYNZCJQY5MKCKCVAKMZNH7G7F7XUUF) |
| testnet | `CDLQR24LLFWXTNGGJVJCRXAF3ZRDWFZRUFTDZ5SJOT2J33CS7DDYP7IU` | [stellar.expert](https://stellar.expert/explorer/testnet/contract/CDLQR24LLFWXTNGGJVJCRXAF3ZRDWFZRUFTDZ5SJOT2J33CS7DDYP7IU) |

Admin: `GBFOFCD3XDANQWSGMHKJJ2V3YXS2QQD7RNC4LMDBVNBTUJOQZ3RLSB3E` · wasm hash `1b6ad9c574e0f5c9e39968f836a410c03adcf057afa93a63d2710bd30fdd53ba`

Skill (API + invoke): [pmll/SKILL.md](https://github.com/drQedwards/pmll/blob/main/SKILL.md)

---

"""
lines = t.splitlines(keepends=True)
try:
    arch_i = next(
        i for i, line in enumerate(lines)
        if line.startswith("## ") and "Architecture" in line
    )
except StopIteration:
    raise SystemExit("architecture heading not found")
if "Stellar commitments (`pmll-anchor`)" not in t:
    lines[arch_i:arch_i] = [section]
    t = "".join(lines)
p.write_text(t)
if "CCF3B64AXLS4OLY5RN4H4K2CFZAYNZCJQY5MKCKCVAKMZNH7G7F7XUUF" not in t:
    raise SystemExit("mainnet contract ID missing after patch")
if t.startswith("# PLACEHOLDER"):
    raise SystemExit("placeholder still present")
print("README bytes", len(t.encode()), "lines", t.count("\n"))
