# **PPM + Q_promises — Unified Documentation**

> *Persistent Package Manager (PPM)* and its companion **Q_promises** library  
> enable deterministic, memory‑aware AI pipelines that span C, Cython and Python.

---

## 📦 Repository Layout

| Path                          | Purpose |
|------------------------------|---------|
| `ppm/`                       | Core Python package manager & CLI |
| `Q_promise_lib/`             | C/Cython implementation of Q‑style thenables |
| `accelerator/`               | CUDA / ROCm kernels for tensor‑core fusion |
| `examples/`                  | Example notebooks & demo pipelines |
| `docs/`                      | Sphinx documentation source |
| `gpt5_build/` _(demo)_       | Minimal C bootstrap showing GPT‑OSS → GPT‑5 |

---

## 🗂 Version History

### 1.0.0 *(January 2024)*
- **Initial PPM core**: basic semantic versioning, dependency graph resolver.
- **Tarball installation** only (`ppm install foo-1.2.3.tgz`).

### 2.0.0 *(June 2024)*
- Added **remote index sync** (JSON registry).
- Introduced **virtual environments** (`ppm venv`).

### 3.0.0 *(February 2025)*
- **Cython build hooks** (`ppm build --cython`).
- Prototype **PMLL hooks** for persistent‑memory AI models.

### 4.0.0 *(July 2025)*
- **Panda data‑manipulation library** bundled (`import ppm.panda`).
- Released **CLI sub‑command** `ppm bench` for micro‑benchmarks.
- File seen at tag `v4.0.0`.

### 5.0.0 *(August 2025)*
- **Unified C core `Q_promises`** (`Q_promises.h/.c/.pyx/.py`).
- Refactored build to **PEP 517 / pyproject.toml**.
- Added `ppm q-trace` for memory‑chain inspection.
- Demo **GPT‑OSS → GPT‑5** bootstrap in `gpt5_build/`.

---

## 🔍 Library Reference (Granular)

### `ppm.core`
```python
from ppm import install, resolve, Version
```
- `install(pkg_spec)` — installs into current environment.  
- `resolve(graph)` — topological sort with semver constraints.  
- **Env‑aware**: respects `$PPM_HOME`, `.ppmrc`.  

### `ppm.panda`
```python
import ppm.panda as pd
df = pd.read_csv("data.csv")
```
- Thin wrapper over Pandas 3.x with lazy‑frame optimisation.  
- Supports **GPU dataframe** via cuDF if available.

### `Q_promises` (C/Cython)
*Header:* `Q_promises.h`
```c
typedef struct QMemNode {
    long index;
    const char* payload;
    struct QMemNode* next;
} QMemNode;

void q_then(QMemNode* head,
            void (*cb)(long,const char*));
```
*Python wrapper*:
```python
import Q_promises
Q_promises.trace(10, lambda i,s: print(i, s))
```
#### Memory safety
- All payload strings duplicated (`strdup`) → freed by `q_mem_free_chain`.
- Thread‑safe if caller provides own synchronisation around callbacks.

### `accelerator`
- `kernels/` NVIDIA PTX & AMD GCN blobs.
- `compile_gpu(model, arch)` — quantises to FP8, fuses attention kernels.

---

## 🚀 Quick Start

```bash
# 1. Install
git clone https://github.com/drQedwards/PPM.git
cd PPM
pip install -e ".[dev,cython]"

# 2. Build C demo
cd gpt5_build && make && ./gpt5_pipeline
```

---

## 🛠 Build Matrix

| Component      | Windows | Linux | macOS | Notes |
|----------------|---------|-------|-------|-------|
| PPM core       | ✔︎       | ✔︎     | ✔︎     | Pure‑python |
| Q_promises     | ✔︎ (MSVC)| ✔︎ (GCC/Clang) | ✔︎ | Requires C11 |
| accelerator    | ❌      | ✔︎ (CUDA/ROCm) | ⚠︎ (Metal) | GPU optional |

---

## 🤝 Contributing
1. Fork & branch (`feature/*`).  
2. Run `pre‑commit run -a`.  
3. Open a PR. GitHub Actions will lint, build wheels, run unit + memory‑chain tests.

---

## 📜 License
*PPM & Q_promises* are released under **MIT License**. GPU kernels under NVIDIA CUDA EULA / AMD ROCm Runtime.

---

_© 2025  Dr. Josef Kurk Edwards & Project Q Contributors_
