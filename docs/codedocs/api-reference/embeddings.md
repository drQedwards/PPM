---
title: "Embeddings"
description: "Reference for the hashing vectorizer, the legacy TF-IDF vectorizer, and vector utilities exported by pmll_memory_mcp."
---

The embeddings module provides the long-term layer's local vectorization primitives.

## Import Path

```python
from pmll_memory_mcp import TfIdfVectorizer, embed, cosine_similarity
```

Source file: `mcp/pmll_memory_mcp/embeddings.py`

## `TfIdfVectorizer`

Constructor:

```python
TfIdfVectorizer() -> None
```

### Property: `vocab_size`

```python
vocab_size: int
```

Current number of terms in the vocabulary.

### `add_document`

```python
add_document(text: str) -> None
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `text` | `str` | — | Document text to fold into corpus statistics. |

### `vectorize`

```python
vectorize(text: str) -> list[float]
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `text` | `str` | — | Text to convert into a normalized TF-IDF vector. |

## Functions

### `embed`

```python
embed(text: str) -> list[float]
```

Returns a stable `EMBED_DIM`-dimensional (128) L2-normalized vector from the module-level `HashingVectorizer` (`get_hasher()`). It does not add the text to any vocabulary, so the same text always maps to the same vector.

### `cosine_similarity`

```python
cosine_similarity(a: list[float], b: list[float]) -> float
```

Returns the cosine of the angle between the vectors, padding the shorter one with zeros. Hashing vectors can have negative components, so the score ranges from `-1.0` to `1.0`.

## Behavior Notes

- `TfIdfVectorizer` gives you an isolated corpus. That is the right choice when you need reproducible vector dimensions inside one test or workflow.
- `embed()` uses the module-level `HashingVectorizer` from `get_hasher()`. There is no shared vocabulary, so stored vectors do not drift as new nodes are added. `TfIdfVectorizer` and `get_vectorizer()` are legacy and are not used for retrieval.
- `cosine_similarity()` zero-pads the shorter vector. Vectors from `embed()` always have the same length, `EMBED_DIM`.

## Example

```python
from pmll_memory_mcp import TfIdfVectorizer, embed, cosine_similarity

vectorizer = TfIdfVectorizer()
vectorizer.add_document("authentication login user")
vectorizer.add_document("authentication login password")

a = vectorizer.vectorize("authentication login user")
b = vectorizer.vectorize("authentication login password")
print(cosine_similarity(a, b))
print(embed("session cache and semantic search"))
```

## Notes

- `embed()` uses a module-level shared vectorizer, while `TfIdfVectorizer()` gives you an isolated one.
- Vector dimensions grow as the vocabulary grows.
- The module also defines `tokenize()`, `get_vectorizer()`, and `reset_vectorizer()` in `mcp/pmll_memory_mcp/embeddings.py`; they are useful for testing and internals even though `__init__.py` does not re-export them.
