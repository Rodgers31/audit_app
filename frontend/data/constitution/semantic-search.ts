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
      idxRes.json() as Promise<{
        dim: number;
        count: number;
        articles: IndexEntry[];
      }>,
    ]);
    const vectors = new Float32Array(bin);
    if (vectors.length !== meta.dim * meta.count) {
      throw new Error(
        `Embedding size mismatch: expected ${meta.dim * meta.count}, got ${vectors.length}`
      );
    }

    // Dynamic import keeps transformers.js out of the initial bundle —
    // visitors who never open the search box pay ~0KB for this feature.
    const { pipeline } = await import('@huggingface/transformers');
    const extract = await pipeline(
      'feature-extraction',
      'Xenova/all-MiniLM-L6-v2',
      { dtype: 'q8' }
    );
    const embed = async (text: string): Promise<Float32Array> => {
      const out = await extract(text, { pooling: 'mean', normalize: true });
      // out.data is a Float32Array of length `dim`
      return out.data as Float32Array;
    };
    return { dim: meta.dim, vectors, entries: meta.articles, embed };
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
