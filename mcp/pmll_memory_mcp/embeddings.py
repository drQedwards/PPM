"""
embeddings.py — Fixed-dimension hashing vectorizer for PMLL memory graph.

Designed to improve context retention and retrieval for coding agents.
Uses the hashing trick so embeddings are stable: querying or embedding new
documents does NOT mutate a global vocabulary. Vectors are always
``EMBED_DIM``-dimensional and L2-normalized.

The legacy ``TfIdfVectorizer`` remains for experiments/export, but ``embed()``
uses the hashing path and never calls ``add_document``.
"""

from __future__ import annotations

import hashlib
import math
import re
import threading
from typing import Dict, List, Optional, Set

EMBED_DIM = 128
_store_lock = threading.RLock()


def tokenize(text: str) -> List[str]:
    """Normalize and tokenize text into lowercase word tokens."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s_-]", " ", text)
    return [t for t in text.split() if len(t) > 1]


def _stable_hash(token: str) -> int:
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "little", signed=False)


class HashingVectorizer:
    """Fixed-dimension feature-hashing vectorizer (no mutable vocabulary)."""

    def __init__(self, dim: int = EMBED_DIM) -> None:
        if dim <= 0:
            raise ValueError("dim must be positive")
        self.dim = dim

    @property
    def vocab_size(self) -> int:
        return self.dim

    def vectorize(self, text: str) -> List[float]:
        tokens = tokenize(text)
        vec = [0.0] * self.dim
        if not tokens:
            return vec
        tf: Dict[str, int] = {}
        for token in tokens:
            tf[token] = tf.get(token, 0) + 1
        max_tf = max(tf.values())
        for term, count in tf.items():
            h = _stable_hash(term)
            idx = h % self.dim
            sign = 1.0 if ((h >> 1) & 1) == 0 else -1.0
            normalized_tf = 0.5 + 0.5 * (count / max_tf)
            vec[idx] += sign * normalized_tf
        return l2_normalize(vec)


class TfIdfVectorizer:
    """Legacy TF-IDF vectorizer (mutable vocab — do not use for retrieval)."""

    def __init__(self) -> None:
        self._vocab: Dict[str, int] = {}
        self._idf: Dict[str, float] = {}
        self._doc_count: int = 0
        self._doc_freq: Dict[str, int] = {}

    @property
    def vocab_size(self) -> int:
        return len(self._vocab)

    def add_document(self, text: str) -> None:
        tokens = tokenize(text)
        seen: Set[str] = set()
        for token in tokens:
            if token not in self._vocab:
                self._vocab[token] = len(self._vocab)
            if token not in seen:
                seen.add(token)
                self._doc_freq[token] = self._doc_freq.get(token, 0) + 1
        self._doc_count += 1
        self._recompute_idf()

    def vectorize(self, text: str) -> List[float]:
        tokens = tokenize(text)
        dim = len(self._vocab)
        if dim == 0:
            return []
        tf: Dict[str, int] = {}
        for token in tokens:
            tf[token] = tf.get(token, 0) + 1
        vec = [0.0] * dim
        max_tf = max(tf.values()) if tf else 1
        for term, count in tf.items():
            idx = self._vocab.get(term)
            if idx is not None:
                normalized_tf = 0.5 + 0.5 * (count / max_tf)
                idf = self._idf.get(term, 1.0)
                vec[idx] = normalized_tf * idf
        return l2_normalize(vec)

    def _recompute_idf(self) -> None:
        for term, df in self._doc_freq.items():
            self._idf[term] = math.log(1 + self._doc_count / (1 + df))


def l2_normalize(vec: List[float]) -> List[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 1e-10:
        return [v / norm for v in vec]
    return list(vec)


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Cosine similarity; pads the shorter vector with zeros so dims align."""
    if not a or not b:
        return 0.0
    n = max(len(a), len(b))
    dot = norm_a = norm_b = 0.0
    for i in range(n):
        av = a[i] if i < len(a) else 0.0
        bv = b[i] if i < len(b) else 0.0
        dot += av * bv
        norm_a += av * av
        norm_b += bv * bv
    denom = math.sqrt(norm_a) * math.sqrt(norm_b)
    return dot / denom if denom > 0 else 0.0


_global_hasher: Optional[HashingVectorizer] = None
_global_vectorizer: Optional[TfIdfVectorizer] = None


def get_hasher() -> HashingVectorizer:
    global _global_hasher
    with _store_lock:
        if _global_hasher is None:
            _global_hasher = HashingVectorizer(EMBED_DIM)
        return _global_hasher


def get_vectorizer() -> TfIdfVectorizer:
    """Legacy accessor — prefer ``get_hasher()`` / ``embed()`` for retrieval."""
    global _global_vectorizer
    with _store_lock:
        if _global_vectorizer is None:
            _global_vectorizer = TfIdfVectorizer()
        return _global_vectorizer


def reset_vectorizer() -> None:
    global _global_hasher, _global_vectorizer
    with _store_lock:
        _global_hasher = None
        _global_vectorizer = None


def embed(text: str) -> List[float]:
    """Stable fixed-dim embedding. Does **not** mutate any global vocabulary."""
    return get_hasher().vectorize(text)
