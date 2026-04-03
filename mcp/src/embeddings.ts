/**
 * embeddings.ts — Self-contained TF-IDF embedding engine for PMLL memory graph.
 *
 * Provides lightweight vector embeddings without external service dependencies.
 * Uses TF-IDF (Term Frequency–Inverse Document Frequency) to convert text into
 * numeric vectors, enabling cosine similarity search across memory nodes.
 *
 * This is designed to work in any environment (Kaggle, Claude, local) without
 * requiring Ollama, OpenAI, or any external embedding API.
 *
 * Architecture:
 *   - Tokenizer: splits text into normalized word tokens
 *   - TF-IDF Vectorizer: builds vocabulary from corpus, generates sparse vectors
 *   - Cosine similarity: compares vector pairs for semantic matching
 */

// ---------------------------------------------------------------------------
// Tokenizer
// ---------------------------------------------------------------------------

/** Normalize and tokenize text into lowercase word tokens. */
export function tokenize(text: string): string[] {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s_-]/g, " ")
    .split(/\s+/)
    .filter((t) => t.length > 1);
}

// ---------------------------------------------------------------------------
// TF-IDF Vectorizer
// ---------------------------------------------------------------------------

/**
 * Self-contained TF-IDF vectorizer that builds a vocabulary from documents
 * and produces fixed-dimension vectors.
 *
 * The vectorizer maintains an internal vocabulary that grows as new documents
 * are added. All vectors are re-normalized after generation.
 */
export class TfIdfVectorizer {
  private _vocab: Map<string, number> = new Map();
  private _idf: Map<string, number> = new Map();
  private _docCount = 0;
  private _docFreq: Map<string, number> = new Map();

  /** Current vocabulary size. */
  get vocabSize(): number {
    return this._vocab.size;
  }

  /**
   * Add a document to the corpus (updates IDF statistics).
   * Call this for each document before generating vectors.
   */
  addDocument(text: string): void {
    const tokens = tokenize(text);
    const seen = new Set<string>();

    for (const token of tokens) {
      if (!this._vocab.has(token)) {
        this._vocab.set(token, this._vocab.size);
      }
      if (!seen.has(token)) {
        seen.add(token);
        this._docFreq.set(token, (this._docFreq.get(token) ?? 0) + 1);
      }
    }

    this._docCount++;
    this._recomputeIdf();
  }

  /**
   * Generate a TF-IDF vector for the given text.
   * Returns a dense array of length `vocabSize`.
   */
  vectorize(text: string): number[] {
    const tokens = tokenize(text);
    const dim = this._vocab.size;
    if (dim === 0) return [];

    // Term frequency
    const tf = new Map<string, number>();
    for (const token of tokens) {
      tf.set(token, (tf.get(token) ?? 0) + 1);
    }

    const vec = new Array(dim).fill(0);
    const maxTf = Math.max(1, ...tf.values());

    for (const [term, count] of tf) {
      const idx = this._vocab.get(term);
      if (idx !== undefined) {
        const normalizedTf = 0.5 + 0.5 * (count / maxTf);
        const idf = this._idf.get(term) ?? 1;
        vec[idx] = normalizedTf * idf;
      }
    }

    // L2-normalize
    return l2Normalize(vec);
  }

  private _recomputeIdf(): void {
    for (const [term, df] of this._docFreq) {
      this._idf.set(term, Math.log(1 + this._docCount / (1 + df)));
    }
  }
}

// ---------------------------------------------------------------------------
// Vector utilities
// ---------------------------------------------------------------------------

/** L2-normalize a vector in-place and return it. */
export function l2Normalize(vec: number[]): number[] {
  let norm = 0;
  for (const v of vec) norm += v * v;
  norm = Math.sqrt(norm);
  if (norm > 1e-10) {
    for (let i = 0; i < vec.length; i++) vec[i] /= norm;
  }
  return vec;
}

/** Cosine similarity between two vectors. */
export function cosineSimilarity(a: number[], b: number[]): number {
  const len = Math.min(a.length, b.length);
  if (len === 0) return 0;

  let dot = 0;
  let normA = 0;
  let normB = 0;
  for (let i = 0; i < len; i++) {
    dot += a[i] * b[i];
    normA += a[i] * a[i];
    normB += b[i] * b[i];
  }

  const denom = Math.sqrt(normA) * Math.sqrt(normB);
  return denom === 0 ? 0 : dot / denom;
}

// ---------------------------------------------------------------------------
// Module-level vectorizer (shared across memory graph operations)
// ---------------------------------------------------------------------------

let _globalVectorizer: TfIdfVectorizer | null = null;

/** Get or create the global TF-IDF vectorizer instance. */
export function getVectorizer(): TfIdfVectorizer {
  if (!_globalVectorizer) {
    _globalVectorizer = new TfIdfVectorizer();
  }
  return _globalVectorizer;
}

/** Reset the global vectorizer (for testing). */
export function resetVectorizer(): void {
  _globalVectorizer = null;
}

/**
 * Generate an embedding for the given text using the global vectorizer.
 * Automatically adds the document to the corpus for IDF computation.
 */
export function embed(text: string): number[] {
  const vectorizer = getVectorizer();
  vectorizer.addDocument(text);
  return vectorizer.vectorize(text);
}
