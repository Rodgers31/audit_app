/**
 * Semantic layer wrapped around the BM25 index.
 *
 * Why: BM25 is great when the user's vocabulary overlaps the text but
 * fails when it doesn't — "how many terms can a president serve?" won't
 * find Article 142 because that article says "two terms" and never uses
 * "limit" or "serve". Embeddings encode meaning rather than token
 * overlap, so a query and its target can be close in vector space even
 * without any shared words.
 *
 * Model: Xenova/all-MiniLM-L6-v2 (384-dim, quantized ~23MB). Runs in the
 * browser via onnxruntime-web / WASM. Cached by the browser after first
 * load; subsequent visits are near-instant.
 *
 * Article vectors are pre-computed by scripts/build-embeddings.mjs and
 * shipped as a 396KB Float32 blob. The runtime only needs to embed the
 * *query* (a few tokens) and dot-product it against the blob.
 *
 * SSR-safety: the transformers library uses WASM and can only run in
 * the browser. Every public entry point checks `typeof window` before
 * touching the pipeline, so importing this file from a server component
 * is harmless — it just resolves to an empty hit list on the server.
 */
import type { ChapterMeta, ConstitutionArticle } from './types';
import { CONSTITUTION_META } from './index';
import embeddingModel from '../../scripts/embedding-model.json';

export interface SemanticHit {
  chapterNumber: number;
  articleNumber: number;
  /** Cosine similarity in [0, 1]. Article vectors are L2-normalised. */
  score: number;
}

interface IndexEntry {
  ch: number;
  art: number;
  title: string;
}

interface LoadedIndex {
  dim: number;
  vectors: Float32Array; // packed [count * dim]
  entries: IndexEntry[];
  embed: (text: string) => Promise<Float32Array>;
}

const EMBEDDING_DIM = 384;

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function refuseEmbedding(reason: string): never {
  // The UI can continue with BM25; keep invalid assets/output observable
  // without logging the user's query or model payload.
  console.warn(`Constitution semantic search unavailable: ${reason}`);
  throw new Error(`Invalid constitution embedding: ${reason}`);
}

function validateVector(values: Float32Array, offset: number, label: string): void {
  let squaredNorm = 0;
  for (let k = 0; k < EMBEDDING_DIM; k++) {
    const value = values[offset + k];
    if (!Number.isFinite(value)) refuseEmbedding(`${label} contains a non-finite value`);
    squaredNorm += value * value;
  }
  // Match the builder's normalization contract. This also refuses zero and
  // oversized finite vectors that would invalidate cosine scoring.
  if (Math.abs(Math.sqrt(squaredNorm) - 1) >= 0.0001) {
    refuseEmbedding(`${label} is not normalized`);
  }
}

function validateIndex(meta: unknown, bin: ArrayBuffer): { vectors: Float32Array; entries: IndexEntry[] } {
  if (!isRecord(meta) || meta.model !== embeddingModel.model || meta.dim !== EMBEDDING_DIM) {
    refuseEmbedding('incompatible index model or dimension');
  }
  // The accepted builder/shipped index omit revision. Preserve that legacy
  // format; any explicitly declared revision must match the pinned encoder.
  // An omitted revision does not authenticate the asset's generation history.
  if ('revision' in meta && meta.revision !== embeddingModel.revision) {
    refuseEmbedding('incompatible index revision');
  }
  if (typeof meta.count !== 'number' || !Number.isSafeInteger(meta.count) || meta.count <= 0 ||
      !Array.isArray(meta.articles) || meta.articles.length !== meta.count) {
    refuseEmbedding('invalid index count or entries');
  }
  if (bin.byteLength !== meta.count * EMBEDDING_DIM * Float32Array.BYTES_PER_ELEMENT) {
    refuseEmbedding('embedding byte size mismatch');
  }
  const entries: IndexEntry[] = [];
  const seen = new Set<number>();
  for (const entry of meta.articles) {
    if (!isRecord(entry) || typeof entry.ch !== 'number' || !Number.isSafeInteger(entry.ch) ||
        typeof entry.art !== 'number' || !Number.isSafeInteger(entry.art) ||
        typeof entry.title !== 'string' || !entry.title.trim()) {
      refuseEmbedding('invalid article entry');
    }
    const chapter = CONSTITUTION_META.find(c => c.number === entry.ch);
    if (!chapter?.articleTitles.some(a => a.number === entry.art) || seen.has(entry.art)) {
      refuseEmbedding('unknown or duplicate article identity');
    }
    seen.add(entry.art);
    entries.push({ ch: entry.ch, art: entry.art, title: entry.title });
  }
  const vectors = new Float32Array(bin);
  for (let i = 0; i < entries.length; i++) validateVector(vectors, i * EMBEDDING_DIM, 'stored vector');
  return { vectors, entries };
}

let INDEX_PROMISE: Promise<LoadedIndex> | null = null;

/**
 * One-time setup: parallel-fetch the vector blob + index, then lazy-load
 * the encoder pipeline. The first call pays the cost (~3-5s on a warm
 * CDN, model bytes are cached after); every later call reuses the same
 * promise.
 */
async function getIndex(): Promise<LoadedIndex> {
  if (INDEX_PROMISE) return INDEX_PROMISE;
  if (typeof window === 'undefined') {
    throw new Error('Semantic search is browser-only');
  }
  INDEX_PROMISE = (async () => {
    const [binRes, idxRes] = await Promise.all([
      fetch('/data/constitution/embeddings.bin'),
      fetch('/data/constitution/embeddings-index.json'),
    ]);
    if (!binRes.ok || !idxRes.ok) {
      throw new Error('Failed to load embedding assets');
    }
    const [bin, meta] = await Promise.all([
      binRes.arrayBuffer(),
      idxRes.json() as Promise<unknown>,
    ]);
    const { vectors, entries } = validateIndex(meta, bin);

    // Dynamic import keeps transformers.js out of the initial bundle —
    // visitors who never open the search box pay ~0KB for this feature.
    const { BertTokenizer, AutoModel, FeatureExtractionPipeline } = await import('@huggingface/transformers');
    const { model: modelId, revision } = embeddingModel;
    // Transformers 4.3.1 discovery requests ignore revision. Load the known
    // BERT tokenizer's two files explicitly so every model request stays pinned.
    const tokenizerFiles = await Promise.all(['tokenizer.json', 'tokenizer_config.json'].map(async (file) => {
      const response = await fetch(`https://huggingface.co/${modelId}/resolve/${revision}/${file}`, {
        signal: AbortSignal.timeout(60000),
      });
      if (!response.ok) throw new Error('Failed to load pinned tokenizer');
      return response.json();
    }));
    const tokenizer = new BertTokenizer(tokenizerFiles[0], tokenizerFiles[1]);
    const model = await AutoModel.from_pretrained(modelId, { dtype: 'q8', revision });
    const extract = new FeatureExtractionPipeline({ task: 'feature-extraction', tokenizer, model });
    const embed = async (text: string): Promise<Float32Array> => {
      const out: unknown = await extract(text, { pooling: 'mean', normalize: true });
      if (!isRecord(out) || !(out.data instanceof Float32Array) || out.data.length !== EMBEDDING_DIM ||
          !Array.isArray(out.dims) || out.dims.length !== 2 || out.dims[0] !== 1 || out.dims[1] !== EMBEDDING_DIM) {
        refuseEmbedding('invalid query vector shape');
      }
      validateVector(out.data, 0, 'query vector');
      return out.data;
    };
    return { dim: EMBEDDING_DIM, vectors, entries, embed };
  })();
  return INDEX_PROMISE;
}

/**
 * Rank every article by cosine similarity to `query`. Returns the top
 * `limit` hits as `{chapterNumber, articleNumber, score}` so callers
 * can merge with or replace BM25 results.
 *
 * Returns [] if the model fails to load — callers should treat this as
 * "semantic unavailable" and fall back to BM25.
 */
export async function semanticSearch(
  query: string,
  limit = 20
): Promise<SemanticHit[]> {
  if (!query.trim() || typeof window === 'undefined') return [];
  let idx: LoadedIndex;
  try {
    idx = await getIndex();
  } catch {
    // Network or runtime failure — swallow and let BM25 carry the weight.
    INDEX_PROMISE = null;
    return [];
  }
  const { dim, vectors, entries, embed } = idx;
  let qVec: Float32Array;
  try {
    qVec = await embed(query);
  } catch {
    return [];
  }

  // Article vectors and qVec are both L2-normalised, so a plain dot
  // product gives cosine similarity. Track the top `limit` scores with
  // a small insertion scan (N=264 × limit ≤ 20 is trivial vs a heap).
  const top: SemanticHit[] = [];
  for (let i = 0; i < entries.length; i++) {
    let sim = 0;
    const off = i * dim;
    for (let k = 0; k < dim; k++) sim += qVec[k]! * vectors[off + k]!;
    if (top.length < limit) {
      top.push({
        chapterNumber: entries[i]!.ch,
        articleNumber: entries[i]!.art,
        score: sim,
      });
      if (top.length === limit) top.sort((a, b) => b.score - a.score);
    } else if (sim > top[top.length - 1]!.score) {
      top[top.length - 1] = {
        chapterNumber: entries[i]!.ch,
        articleNumber: entries[i]!.art,
        score: sim,
      };
      // Bubble up — top is already sorted descending.
      for (let j = top.length - 1; j > 0 && top[j]!.score > top[j - 1]!.score; j--) {
        const tmp = top[j]!;
        top[j] = top[j - 1]!;
        top[j - 1] = tmp;
      }
    }
  }
  if (top.length < limit) top.sort((a, b) => b.score - a.score);
  return top;
}

/**
 * Hint for callers that want to show a "preparing smart search…" spinner
 * on first use. Resolves once the index + model are ready.
 */
export function warmSemanticIndex(): Promise<void> {
  if (typeof window === 'undefined') return Promise.resolve();
  return getIndex().then(
    () => undefined,
    () => undefined
  );
}

/** Resolve a SemanticHit back to the full meta object (sync). */
export function resolveMeta(hit: SemanticHit): ChapterMeta | undefined {
  return CONSTITUTION_META.find((c) => c.number === hit.chapterNumber);
}

/** Resolve to the article meta stub when only the number is needed. */
export function resolveArticleMeta(
  hit: SemanticHit
): { number: number; title: string } | undefined {
  const chapter = resolveMeta(hit);
  return chapter?.articleTitles.find((a) => a.number === hit.articleNumber);
}

/** Test-only: drop the cached index so unit tests can re-stub fetch. */
export function __resetSemanticIndex() {
  INDEX_PROMISE = null;
}

// Re-export types callers need without importing from the index module.
export type { ChapterMeta, ConstitutionArticle };
