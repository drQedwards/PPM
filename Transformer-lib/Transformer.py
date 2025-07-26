# Transformer.py
# Python-side engine used by the C wrapper. Uses PPM to ensure dependencies.
from __future__ import annotations

import os
import sys
import subprocess
from typing import Optional, List

def _ensure_deps():
    try:
        import transformers  # noqa: F401
        import torch  # noqa: F401
        return
    except Exception:
        pass

    # Try PPM first if available
    if _which("ppm"):
        try:
            subprocess.run(
                ["ppm", "ensure", "transformers", "--gpu", "auto"],
                check=True
            )
            import transformers, torch  # noqa: F401
            return
        except Exception:
            # fall back to pip
            pass

    # Fallback: pip install
    subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"], check=False)
    subprocess.run([sys.executable, "-m", "pip", "install", "transformers", "torch"], check=True)

def _which(name: str) -> str | None:
    from shutil import which
    return which(name)

_ensure_deps()

import torch
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    AutoModel,
    pipeline,
)

_DEFAULT_EMBED = "sentence-transformers/all-MiniLM-L6-v2"

def _device_from_str(device: Optional[str]) -> str:
    if not device or device == "auto":
        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
        return "cpu"
    return device

class Engine:
    def __init__(self,
                 model_id: Optional[str] = None,
                 device: Optional[str] = None,
                 use_8bit: bool = False,
                 embed_model_id: Optional[str] = None):
        self.model_id = model_id or "gpt2"
        self.device_str = _device_from_str(device)
        self.embed_model_id = embed_model_id or _DEFAULT_EMBED

        dtype = torch.float16 if self.device_str in ("cuda", "mps") else torch.float32

        load_kwargs = {}
        if use_8bit:
            # Only works if bitsandbytes is available; ignore otherwise.
            try:
                import bitsandbytes as bnb  # noqa: F401
                load_kwargs["load_in_8bit"] = True
                load_kwargs["device_map"] = "auto"
            except Exception:
                # silently ignore; fall back to normal dtype
                pass

        # Generation pipeline
        self.gen_tokenizer = AutoTokenizer.from_pretrained(self.model_id, use_fast=True)
        self.gen_model = AutoModelForCausalLM.from_pretrained(
            self.model_id,
            torch_dtype=dtype,
            **load_kwargs,
        )
        self.generator = pipeline(
            "text-generation",
            model=self.gen_model,
            tokenizer=self.gen_tokenizer,
            device=0 if self.device_str == "cuda" else -1,
        )

        # Embedding model
        self.emb_tokenizer = AutoTokenizer.from_pretrained(self.embed_model_id, use_fast=True)
        self.emb_model = AutoModel.from_pretrained(self.embed_model_id, torch_dtype=dtype)
        self.emb_model.eval()
        if self.device_str != "cpu":
            self.emb_model.to(self.device_str)

    @torch.inference_mode()
    def generate(self, prompt: str, max_new_tokens: int = 128, temperature: float = 0.7) -> str:
        out = self.generator(
            prompt,
            max_new_tokens=max_new_tokens,
            do_sample=True,
            temperature=max(0.0, float(temperature)),
            pad_token_id=self.gen_tokenizer.eos_token_id,
        )
        # pipeline returns list of dicts
        return out[0]["generated_text"]

    @torch.inference_mode()
    def embed(self, text: str) -> List[float]:
        toks = self.emb_tokenizer(text, return_tensors="pt", truncation=True, padding=True)
        if self.device_str != "cpu":
            toks = {k: v.to(self.device_str) for k, v in toks.items()}
        outputs = self.emb_model(**toks)
        # Mean pool over sequence length
        last_hidden = outputs.last_hidden_state  # [B, T, H]
        mask = toks["attention_mask"].unsqueeze(-1).expand(last_hidden.size()).float()
        masked = last_hidden * mask
        summed = masked.sum(dim=1)
        counts = mask.sum(dim=1).clamp(min=1e-9)
        mean = summed / counts
        vec = mean[0].detach().to("cpu").float().numpy().tolist()
        return vec
