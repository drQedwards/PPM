---
title: "Embeddings"
description: "Reference for the TF-IDF vectorizer and vector utilities exported by pmll_memory_mcp."
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

Adds the text to the module-level vectorizer and returns its vector.

### `cosine_similarity`

```python
cosine_similarity(a: list[float], b: list[float]) -> float
```

Returns a score between `0.0` and `1.0` for aligned non-negative vectors.

## Behavior Notes

- `TfIdfVectorizer` gives you an isolated corpus. That is the right choice when you need reproducible vector dimensions inside one test or workflow.
- `embed()` uses the module-level singleton managed by `get_vectorizer()` in the source. That is convenient for the graph layer because every new node contributes to the shared vocabulary.
- `cosine_similarity()` only compares the overlapping vector length. In practice that works because both vectors usually come from the same vectorizer instance.

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
