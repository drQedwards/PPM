# ppm/hooks/transformers_policy.py
from dataclasses import dataclass
import platform

@dataclass
class BackendChoice:
    name: str    # "cpu" | "cu121" | "cu122" | "rocm6"
    index: str

def detect_backend(user_pref: str | None) -> BackendChoice:
    # Respect explicit flags first
    if user_pref in {"cpu","cu121","cu122","rocm6"}:
        return _map_backend(user_pref)

    # auto-detect
    try:
        import torch
        if torch.version.cuda:      # running env already has torch w/ CUDA
            return _map_backend("cu121")  # default CUDA; refine if needed
    except Exception:
        pass

    # Lightweight CUDA probe (no torch yet)
    if _has_nvidia_gpu():
        return _map_backend("cu121")
    return _map_backend("cpu")

def _has_nvidia_gpu() -> bool:
    # Fast probe: look for /proc/driver/nvidia or nvidia-smi
    import shutil, os
    if shutil.which("nvidia-smi"): return True
    return os.path.exists("/proc/driver/nvidia/version")

def _map_backend(name: str) -> BackendChoice:
    INDEXES = {
        "cpu":   "https://download.pytorch.org/whl/cpu",
        "cu121": "https://download.pytorch.org/whl/cu121",
        "cu122": "https://download.pytorch.org/whl/cu122",
        "rocm6": "https://download.pytorch.org/whl/rocm6.0",
    }
    return BackendChoice(name=name, index=INDEXES[name])
