/**
 * embeddings.ts — Fixed-dimension hashing vectorizer for PMLL memory graph.
 *
 * Designed to improve context retention and retrieval for coding agents.
 * `embed()` is stable: it does NOT mutate a global TF-IDF vocabulary.
 */

export const EMBED_DIM = 128;

export function tokenize(text: string): string[] {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s_-]/g, " ")
    .split(/\s+/)
    .filter((t) => t.length > 1);
}

function stableHash(token: string): number {
  // FNV-1a 32-bit
  let h = 0x811c9dc5;
  for (let i = 0; i < token.length; i++) {
    h ^= token.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

export function l2Normalize(vec: number[]): number[] {
  let norm = 0;
  for (const v of vec) norm += v * v;
  norm = Math.sqrt(norm);
  if (norm > 1e-10) {
    return vec.map((v) => v / norm);
  }
  return vec.slice();
}

export function cosineSimilarity(a: number[], b: number[]): number {
  if (a.length === 0 || b.length === 0) return 0;
  const n = Math.max(a.length, b.length);
  let dot = 0, normA = 0, normB = 0;
  for (let i = 0; i < n; i++) {
    const av = i < a.length ? a[i] : 0;
    const bv = i < b.length ? b[i] : 0;
    dot += av * bv;
    normA += av * av;
    normB += bv * bv;
  }
  const denom = Math.sqrt(normA) * Math.sqrt(normB);
  return denom === 0 ? 0 : dot / denom;
}

/** Legacy TF-IDF (mutable vocab) — do not use for retrieval. */
export class TfIdfVectorizer {
  private _vocab: Map<string, number> = new Map();
  private _idf: Map<string, number> = new Map();
  private _docCount = 0;
  private _docFreq: Map<string, number> = new Map();
  get vocabSize(): number { return this._vocab.size; }
  addDocument(text: string): void {
    const tokens = tokenize(text);
    const seen = new Set<string>();
    for (const token of tokens) {
      if (!this._vocab.has(token)) this._vocab.set(token, this._vocab.size);
      if (!seen.has(token)) {
        seen.add(token);
        this._docFreq.set(token, (this._docFreq.get(token) ?? 0) + 1);
      }
    }
    this._docCount++;
    for (const [term, df] of this._docFreq) {
      this._idf.set(term, Math.log(1 + this._docCount / (1 + df)));
    }
  }
  vectorize(text: string): number[] {
    const tokens = tokenize(text);
    const dim = this._vocab.size;
    if (dim === 0) return [];
    const tf = new Map<string, number>();
    for (const token of tokens) tf.set(token, (tf.get(token) ?? 0) + 1);
    const vec = new Array(dim).fill(0);
    const maxTf = Math.max(1, ...tf.values());
    for (const [term, count] of tf) {
      const idx = this._vocab.get(term);
      if (idx !== undefined) {
        const normalizedTf = 0.5 + 0.5 * (count / maxTf);
        vec[idx] = normalizedTf * (this._idf.get(term) ?? 1);
      }
    }
    return l2Normalize(vec);
  }
}

export class HashingVectorizer {
  constructor(public readonly dim: number = EMBED_DIM) {
    if (dim <= 0) throw new Error("dim must be positive");
  }
  get vocabSize(): number { return this.dim; }
  vectorize(text: string): number[] {
    const tokens = tokenize(text);
    const vec = new Array(this.dim).fill(0);
    if (tokens.length === 0) return vec;
    const tf = new Map<string, number>();
    for (const token of tokens) tf.set(token, (tf.get(token) ?? 0) + 1);
    const maxTf = Math.max(...tf.values());
    for (const [term, count] of tf) {
      const h = stableHash(term);
      const idx = h % this.dim;
      const sign = ((h >>> 1) & 1) === 0 ? 1 : -1;
      const normalizedTf = 0.5 + 0.5 * (count / maxTf);
      vec[idx] += sign * normalizedTf;
    }
    return l2Normalize(vec);
  }
}

let _globalHasher: HashingVectorizer | null = null;
let _globalVectorizer: TfIdfVectorizer | null = null;

export function getHasher(): HashingVectorizer {
  if (!_globalHasher) _globalHasher = new HashingVectorizer(EMBED_DIM);
  return _globalHasher;
}

export function getVectorizer(): TfIdfVectorizer {
  if (!_globalVectorizer) _globalVectorizer = new TfIdfVectorizer();
  return _globalVectorizer;
}

export function resetVectorizer(): void {
  _globalHasher = null;
  _globalVectorizer = null;
}

/** Stable fixed-dim embedding — does not mutate any global vocabulary. */
export function embed(text: string): number[] {
  return getHasher().vectorize(text);
}
