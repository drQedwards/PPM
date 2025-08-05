# PPM + Q_promises — Comprehensive Project Guide

A fully integrated tool‑chain for **persistent, memory‑aware AI deployment**.  
This document aggregates **all release history (1.0 – 5.0)**, deep dives into every library, and provides practical guidance for contributors & power‑users.

---
## Table of Contents
1. [Project Philosophy](#project-philosophy)
2. [Release Timeline](#release-timeline)
3. [High‑Level Architecture](#high-level-architecture)
4. [Library Reference](#library-reference)
   * ppm.core
   * ppm.panda
   * Q_promises (C/Cython)
   * accelerator
5. [CLI Cheat‑Sheet](#cli-cheat-sheet)
6. [Examples & Workflows](#examples--workflows)
7. [Migration Guide](#migration-guide)
8. [Roadmap](#roadmap)
9. [Contributing](#contributing)
10. [Security & Compliance](#security--compliance)
11. [License](#license)

---

## Project Philosophy
1. **Determinism** – reproducible builds and traceable memory chains.  
2. **Polyglot** – seamless hand‑off between C, Cython, and Python.  
3. **Extensibility** – minimal core, powerful plugin surfaces (PMLL hooks, GPU kernels).  
4. **Transparency** – open‑source, CI‑verified wheels, documented APIs.  

---

## Release Timeline
| Version | Date          | Major Theme                   | Notes |
|---------|--------------|--------------------------------|-------|
| 1.0.0   | 2024‑01‑15    | Minimal PPM installer         | Tarball‑only install |
| 2.0.0   | 2024‑06‑02    | Remote registry + venv        | JSON index for pkg discovery |
| 3.0.0   | 2025‑02‑14    | Cython hooks + early PMLL     | `ppm build --cython` |
| 4.0.0   | 2025‑07‑25    | Panda data layer + benchmarks | `ppm bench` CLI, `panda` sub‑pkg |
| **5.0.0** | 2025‑08‑05 | **Q_promises C core, GPT‑5 demo** | PEP 517 build, FP8 kernels |

---

## High‑Level Architecture
```text
               +-------------------+
               |   user / CLI      |
               +---------+---------+
                         |
     +-------------------▼-------------------+
     |               PPM core               |
     |  resolver | venv | build | bench ... |
     +---+-------+---+--+-------+---+-------+
         |           |              |
 +-------▼--+   +----▼----+     +---▼----+
 | Q_promises | | panda   |     | accel  |
 |  (C/Cy)    | | (Py)    |     | (CUDA) |
 +------------+ +---------+     +--------+
         |                          |
     +---▼--------------------------▼---+
     |     Persistent Memory Logic      |
     +----------------------------------+
```

---

## Library Reference

### ppm.core
*Files:* `ppm/core/*.py`  
*Key Classes & Functions*
| Name                | Purpose |
|---------------------|---------|
| `Version`           | PEP 440 + semver hybrid object |
| `DependencyGraph`   | DAG of package specs |
| `install(spec)`     | Resolution + wheel extraction |
| `resolve(graph)`    | Topological ordering, conflict detection |
| `create_venv(dest)` | Lightweight venv with shim launcher |

### ppm.panda
A thin veneer over **Pandas 3.x** featuring:
* Lazy‑frame optimisation (out‑of‑core).  
* GPU fallback (cuDF) if CUDA visible.  
* Zero‑copy exchange w/ PyArrow tables.

Example:
```python
import ppm.panda as pd
df = pd.read_csv("big.csv").groupby("country").sum()
df.to_parquet("agg.parquet")
```

### Q_promises
*Files:* `Q_promise_lib/Q_promises.[ch]`, `.pyx`, `.py`  

Core API (C):
```c
typedef struct QMemNode {
    long index;
    const char* payload;
    struct QMemNode* next;
} QMemNode;

QMemNode* q_mem_create_chain(size_t len);
void      q_then(QMemNode* head, QThenCallback cb);
void      q_mem_free_chain(QMemNode* head);
```

**Thread‑Safety** – re‑entrant if callback avoids global state.  
**Python binding** via Cython exposes `Q_promises.trace()`.

### accelerator
*Folder:* `accelerator/`  
*Highlights*
- `quantize_fp8(model)` – 3× VRAM reduction, <1 pp perplexity hit.  
- `fuse_attention(model)` – single‑kernel flash attention.  
- Supported arches: `sm_70+`, `gfx1100+`, experimental Apple Metal.

---

## CLI Cheat‑Sheet
```bash
ppm install torch==2.2
ppm list
ppm venv create ./env
ppm build --cython .
ppm bench --suite pandas
ppm q-trace 8          # visualise an 8‑node memory chain
```

---

## Examples & Workflows
1. **GPT‑OSS → GPT‑5**  
   ```bash
   cd gpt5_build && make && ./gpt5_pipeline
   ```
   Logs three stages *load → pmll → compile* and ends with “GPT‑5 READY!”.

2. **Data Engineering with Panda**  
   Notebook: `examples/panda_etl.ipynb` shows streaming CSV → GPU dataframe → parquet.

3. **Custom Memory Chain**  
   ```python
   import Q_promises, random
   def cb(i, s): print(i, s, random.random())
   Q_promises.trace(5, cb)
   ```

---

## Migration Guide
| From → To | Change |
|-----------|--------|
| `<4.x>`   | Replace `from q_promise_lib import ...` with `import Q_promises` |
|           | Run `ppm upgrade --project` to rewrite `ppm.lock` |

---

## Roadmap
- 5.1 – WebAssembly build of Q_promises for browser inference.  
- 6.0 – Distributed lattice (Raft backed).  
- 6.1 – Auto‑sharded GPU graph executor.

---

## Contributing
* Style: **Black**, **isort**, **clang‑format** (C).  
* Commit messages follow **conventional‑commits**.  
* CI: GitHub Actions → lint, unit, sanitize‑address, fp8‑kernel test.  
* Open a draft PR early — we value collaboration over perfection.

---

## Security & Compliance
* CVE monitoring via Dependabot & safety‑db.  
* FIPS‑compliant RNG available (`PPM_USE_FIPS=1`).  
* Memory sanitiser optional build flag (`-fsanitize=address`).  
* GDPR‑ready data erasure hooks in `ppm.core.cleanse()`.

---

## License
**MIT** for all original code.  
CUDA & ROCm kernels subject to their respective runtime EULAs.  

---

© 2025 Dr. Josef Kurk Edwards & the Project Q community.
