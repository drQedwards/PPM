# ppm Command‑Line Interface (CLI)

The **ppm CLI** is a multi‑language front‑end for the *Persistent Package Manager*.
It wraps the underlying `ppm_core` resolver / fetcher and exposes a single
ergonomic command:

```bash
ppm import <package>[==version] [options]
```

Four drop‑in runners keep behaviour identical across ecosystems:

| Runner  | File            | Purpose                              |
|---------|-----------------|--------------------------------------|
| CPU     | `CLI.c`         | Reference implementation, POSIX‑only |
| Python  | `CLI.py`        | Quick scripts & unit tests           |
| Cython  | `CLI.pyx`       | Fast batched imports (7‑10× Python)  |
| CUDA    | `CLI.cu`        | GPU SHA‑256 integrity checker        |

---

## ✨  Key Features
* **One‑liner install**: `ppm import numpy==2.0.0`  
* **Auto‑scan** dependencies in a script:**  
  `ppm import --from app.py`
* **GPU parallel hashing** for thousands of wheels in seconds.
* **Thread‑safe** cache (mutex protected, multi‑process safe).
* Config via **TOML** at `~/.config/ppm/ppm.toml`.
* **Rich output**: `--verbose`, `--dry-run`, `--json`.

---

## 🔧  Prerequisites
* **C compiler**: GCC 9+, Clang 11+, or MSVC 19.3+
* **Python** 3.8+
* Optional **CUDA** 11.4+ for GPU hashing

---

## 🏗️  Building from Source
Clone the repo and install system‑wide:

```bash
git clone https://github.com/drQedwards/PPM.git
cd PPM

# Core + CPU CLI
make -C src cpu

# CUDA variant (optional)
make -C src gpu       # requires nvcc

# Python shim & Cython wheel
pip install .         # builds and installs `ppm` Python package
```

Produced binaries land in `bin/`:

```bash
ls bin/
ppm         # CPU
ppm_gpu     # CUDA (auto‑detected at runtime)
```

---

## 🚀  Quick Start

```bash
# Install latest version
ppm import requests -v

# Install specific version
ppm import pandas==3.0.1

# Scan your script for imports and install them all
ppm import --from server.py

# JSON log for tooling
ppm import flask --json > log.json
```

Check the populated cache:

```bash
tree ~/.cache/ppm/
```

---

## 🖥️  GPU Acceleration

When `ppm_gpu` detects an available CUDA device, each
downloaded archive is checksummed inside a dedicated thread‑block.
For machines without CUDA the tool gracefully falls back to the CPU binary.

Benchmark on RTX 4070:

| Files | Serial (CPU) | CUDA (GPU) |
|------:|-------------:|-----------:|
| 1 000 |     14.9 s   | **1.3 s**  |
|10 000 |    153.2 s   | **11.6 s** |

---

## 🧩  Embedding Examples

### C
```c
#include <ppm/CLI.h>
int main(int argc, char **argv) {
    return ppm_cli_run(argc, argv);   /* delegate to built‑in parser */
}
```

### Python
```python
from ppm import cli
cli.main(["import", "numpy", "--verbose"])
```

### Cython
```cython
from ppm._cli cimport import_packages
import_packages(["numpy", "scipy"], True)
```

---

## ⚙️  Configuration

`~/.config/ppm/ppm.toml` supports:

```toml
cache_dir = "/mnt/ssd/ppm"
index_url = "https://pypi.org/simple"
retries   = 3
gpu       = true     # auto if omitted
```

---

## 💻  Command Reference

```text
ppm import [options]  PKG[==VER] …
  -f, --from <file.py>  scan Python file for imports
  -v, --verbose         progress output
  --json                machine‑readable log
  --dry-run             resolve only, do not download
  -h, --help            show help
```

---

## 🧑‍💻  Contributing
1. Fork & branch from `main`.
2. `make test` – all unit tests must pass.
3. Submit PR with **signed commit** and descriptive message.

---

## 📄  License
ppm is released under the **MIT License**.  
© 2025 Dr. Josef K. Edwards & Contributors.
