"""
embeddings.py — Self-contained TF-IDF embedding engine for PMLL memory graph.

Provides lightweight vector embeddings without external service dependencies.
Uses TF-IDF (Term Frequency–Inverse Document Frequency) to convert text into
numeric vectors, enabling cosine similarity search across memory nodes.

Designed to work in any environment (Kaggle, Claude, local) without
requiring Ollama, OpenAI, or any external embedding API.
"""

from __future__ import annotations

import math
import re
from typing import Dict, List, Optional, Set


def tokenize(text: str) -> List[str]:
    """Normalize and tokenize text into lowercase word tokens."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s_-]", " ", text)
    return [t for t in text.split() if len(t) > 1]


class TfIdfVectorizer:
    """Self-contained TF-IDF vectorizer that builds vocabulary from documents.

    The vectorizer maintains an internal vocabulary that grows as new documents
    are added. All vectors are L2-normalized after generation.
    """

    def __init__(self) -> None:
        self._vocab: Dict[str, int] = {}
        self._idf: Dict[str, float] = {}
        self._doc_count: int = 0
        self._doc_freq: Dict[str, int] = {}

    @property
    def vocab_size(self) -> int:
        """Current vocabulary size."""
        return len(self._vocab)

    def add_document(self, text: str) -> None:
        """Add a document to the corpus (updates IDF statistics)."""
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
        """Generate a TF-IDF vector for the given text."""
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
    """L2-normalize a vector in-place and return it."""
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 1e-10:
        for i in range(len(vec)):
            vec[i] /= norm
    return vec


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Cosine similarity between two vectors."""
    length = min(len(a), len(b))
    if length == 0:
        return 0.0

    dot = sum(a[i] * b[i] for i in range(length))
    norm_a = math.sqrt(sum(a[i] * a[i] for i in range(length)))
    norm_b = math.sqrt(sum(b[i] * b[i] for i in range(length)))

    denom = norm_a * norm_b
    return dot / denom if denom > 0 else 0.0


# ---------------------------------------------------------------------------
# Module-level vectorizer (shared across memory graph operations)
# ---------------------------------------------------------------------------

_global_vectorizer: Optional[TfIdfVectorizer] = None


def get_vectorizer() -> TfIdfVectorizer:
    """Get or create the global TF-IDF vectorizer instance."""
    global _global_vectorizer
    if _global_vectorizer is None:
        _global_vectorizer = TfIdfVectorizer()
    return _global_vectorizer


def reset_vectorizer() -> None:
    """Reset the global vectorizer (for testing)."""
    global _global_vectorizer
    _global_vectorizer = None


def embed(text: str) -> List[float]:
    """Generate an embedding for the given text using the global vectorizer."""
    vectorizer = get_vectorizer()
    vectorizer.add_document(text)
    return vectorizer.vectorize(text)
