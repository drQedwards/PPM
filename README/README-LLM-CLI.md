# LLM‑CLI‑BUILDER‑PPM

**Seamlessly stitch together local LLM weights (Ollama) and Python runtime
dependencies (PPM) in one portable tool.**

*Version 0.1 — generated 2025-08-07*

---

## 📦 What is it?

`llm` is a tiny C++17 utility (`LLM-CLI-BUILDER-PPM.cpp`) that:

1. **Pulls** a model with `ollama pull <model>`  
2. **Installs** any required Python wheels via `ppm import`  
3. **Logs** provenance (SHA‑256 digests, timestamps) into the shared ppm
   manifest so builds are fully reproducible.

End result: a single command gives you an immediately runnable model
environment:

```bash
llm build llama3:instruct --dep transformers==4.42.0 --dep accelerate -v
ollama run llama3:instruct          # now “just works”
```

---

## ✨ Features

| Component | Capability |
|-----------|------------|
| **Ollama** | Fetches GGUF/GGML weights; supports remote, local or custom tags |
| **PPM** | Installs wheels/tarballs into global persistent cache (`~/.cache/ppm`) |
| **Provenance** | Computes SHA‑256 on both model weights & wheels; stores to SQLite |
| **Verbose / JSON** | All core `ppm` flags pass‑through (`--verbose`, `--json`, `--dry-run`) |
| **Dependencies** | `--dep` flags or a `requirements.txt` via `llm deps` |

---

## 🔧 Build

### Prerequisites
* C++17 compiler (GCC 9+, Clang 12+, MSVC 19.3+)
* Ollama installed & on `$PATH`
* PPM 6.0.0+ (CPU or GPU build)

### Compile

```bash
g++ -std=c++17 -Iinclude -Llib -lppm_core \
    -o llm src/LLM-CLI-BUILDER-PPM.cpp
```

### Optional: CMake

```cmake
find_package(ppm_core REQUIRED)
add_executable(llm src/LLM-CLI-BUILDER-PPM.cpp)
target_link_libraries(llm PRIVATE ppm_core)
```

---

## 🚀 Usage

```text
llm build <model> [--dep <spec>]... [--verbose]
llm deps  <requirements.txt> [--verbose]

Options:
  --dep <name[==ver]>   Extra Python dependency to install
  -v, --verbose         Chatty output
  -h, --help            Print help
```

Examples:

```bash
# Basic
llm build llama3

# Exact transformers version
llm build llama3:instruct --dep transformers==4.42.0

# Install deps from requirements file
llm deps requirements.txt -v
```

---

## 🖥️ GPU Integrity Check

If `ppm_gpu` exists and CUDA is available, every downloaded file (wheel or
tarball) is hashed in parallel on the GPU, providing 10–20× speedups for large
libraries.

---

## 🗄️ Cache Layout

```
~/.cache/ppm/
├── wheels/
│   └── transformers/4.42.0/<sha256>.whl
└── models/
    └── llama3/<sha256>/...
```

Weights and Python packages live side‑by‑side: no duplication, easy cleanup.

---

## 🧩 Embedding in Your Project

### Python hook

```python
import subprocess
subprocess.check_call(["llm", "build", "mistral"])
```

### C++ call

```cpp
#include <cstdlib>
int main() {
    return std::system("llm build llama3:8b -v");
}
```

---

## ⚙️ Configuration

`~/.config/ppm/ppm.toml` supports:

```toml
cache_dir = "/mnt/ssd/ppm"
index_url = "https://pypi.org/simple"
retries   = 3
gpu.hash  = "sha256"
```

---

## 🧑‍💻 Contributing

1. Fork repo & open PR against `main`.  
2. Ensure `make test` passes (GoogleTest suite).  
3. Sign commits (`git commit -s`).  

---

## 📄 License

MIT License — © 2025 Dr. Josef Kurk Edwards & Contributors.
