import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import manifest from '../scripts/embedding-model.json';

// Admission doubles only. Real browser WASM is exercised separately.
jest.mock('@huggingface/transformers', () => ({
  BertTokenizer: jest.fn(),
  AutoModel: { from_pretrained: jest.fn().mockResolvedValue({}) },
  FeatureExtractionPipeline: jest.fn(),
}));

const originalFetch = global.fetch;
const originalTimeout = AbortSignal.timeout;
let warning: jest.SpyInstance;

function vector(length = 384, first = 1): Float32Array<ArrayBuffer> {
  const values = new Float32Array(length);
  values[0] = first;
  return values;
}

function metadata() {
  return {
    model: manifest.model, revision: manifest.revision, dim: 384, count: 1,
    articles: [{ ch: 9, art: 142, title: 'Term of President' }],
  };
}

function assets(...inputs: [unknown?, ArrayBuffer?]) {
  const meta = inputs.length ? inputs[0] : metadata();
  const bin = inputs[1] ?? vector().buffer;
  global.fetch = jest.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith('embeddings.bin')) return { ok: true, arrayBuffer: async () => bin } as Response;
    if (url.endsWith('embeddings-index.json')) return { ok: true, json: async () => meta } as Response;
    return { ok: true, json: async () => ({}) } as Response;
  });
}

async function encoder(...outputs: unknown[]) {
  const output = outputs.length ? outputs[0] : { data: vector(), dims: [1, 384] };
  const library = await import('@huggingface/transformers');
  const extract = jest.fn().mockResolvedValue(output);
  (library.FeatureExtractionPipeline as jest.Mock).mockImplementation(() => extract);
  return { library, extract };
}

beforeEach(() => {
  jest.resetModules();
  warning = jest.spyOn(console, 'warn').mockImplementation(() => {});
  Object.defineProperty(AbortSignal, 'timeout', { configurable: true, value: () => new AbortController().signal });
});
afterEach(() => {
  warning.mockRestore();
  global.fetch = originalFetch;
  Object.defineProperty(AbortSignal, 'timeout', { configurable: true, value: originalTimeout });
});

test('compatible explicit model revision keeps Article 142 ranking and cached loader', async () => {
  assets();
  const { library, extract } = await encoder();
  const { semanticSearch } = await import('../data/constitution/semantic-search');
  for (const query of ['presidential terms', 'how many terms can a president serve?']) {
    expect(await semanticSearch(query)).toEqual([{ chapterNumber: 9, articleNumber: 142, score: 1 }]);
  }
  expect(library.AutoModel.from_pretrained).toHaveBeenCalledTimes(1);
  expect(extract).toHaveBeenCalledTimes(2);
  expect(warning).not.toHaveBeenCalled();
});

test('committed legacy index without a revision retains finite Article 142 ranking', async () => {
  const meta = JSON.parse(readFileSync(join(process.cwd(), 'public/data/constitution/embeddings-index.json'), 'utf8'));
  const binary = readFileSync(join(process.cwd(), 'public/data/constitution/embeddings.bin'));
  const bin = Uint8Array.from(binary).buffer;
  const offset = meta.articles.findIndex((entry: { art: number }) => entry.art === 142) * 384;
  const query = new Float32Array(bin).slice(offset, offset + 384);
  expect(meta).not.toHaveProperty('revision');
  assets(meta, bin);
  await encoder({ data: query, dims: [1, 384] });
  const { semanticSearch } = await import('../data/constitution/semantic-search');
  const hits = await semanticSearch('presidential terms');
  expect(hits[0].articleNumber).toBe(142);
  expect(hits[0].score).toBeCloseTo(1, 5);
  expect(hits.every(hit => Number.isFinite(hit.score))).toBe(true);
  expect(warning).not.toHaveBeenCalled();
});

const invalidMetadata: [string, () => unknown][] = [
  ['null', () => null], ['absent', () => undefined], ['array', () => []], ['string', () => 'index'],
  ['missing model', () => ({ ...metadata(), model: undefined })],
  ['other model', () => ({ ...metadata(), model: 'unrelated/model' })],
  ['other revision', () => ({ ...metadata(), revision: 'a'.repeat(40) })],
  ['mutable revision', () => ({ ...metadata(), revision: 'main' })],
  ['null revision', () => ({ ...metadata(), revision: null })],
  ['empty revision', () => ({ ...metadata(), revision: '' })],
  ['boolean dimension', () => ({ ...metadata(), dim: true })],
  ['string dimension', () => ({ ...metadata(), dim: '384' })],
  ['fractional dimension', () => ({ ...metadata(), dim: 384.5 })],
  ['nonfinite dimension', () => ({ ...metadata(), dim: Infinity })],
  ['zero dimension', () => ({ ...metadata(), dim: 0 })],
  ['negative count', () => ({ ...metadata(), count: -1 })],
  ['empty count', () => ({ ...metadata(), count: 0, articles: [] })],
  ['boolean count', () => ({ ...metadata(), count: true })],
  ['string count', () => ({ ...metadata(), count: '1' })],
  ['fractional count', () => ({ ...metadata(), count: 1.5 })],
  ['unsafe count', () => ({ ...metadata(), count: Number.MAX_SAFE_INTEGER + 1 })],
  ['entry count mismatch', () => ({ ...metadata(), articles: [] })],
  ['absent entries', () => ({ ...metadata(), articles: undefined })],
  ['object entries', () => ({ ...metadata(), articles: {} })],
  ['null entry', () => ({ ...metadata(), articles: [null] })],
  ['unknown chapter', () => ({ ...metadata(), articles: [{ ch: 99, art: 142, title: 'Terms' }] })],
  ['wrong chapter for article', () => ({ ...metadata(), articles: [{ ch: 1, art: 142, title: 'Terms' }] })],
  ['boolean article', () => ({ ...metadata(), articles: [{ ch: 9, art: true, title: 'Terms' }] })],
  ['absent title', () => ({ ...metadata(), articles: [{ ch: 9, art: 142 }] })],
  ['empty title', () => ({ ...metadata(), articles: [{ ch: 9, art: 142, title: '' }] })],
];

test.each(invalidMetadata)('invalid index %s is unavailable before model loading', async (_label, makeMeta) => {
  assets(makeMeta());
  const { library, extract } = await encoder();
  const { semanticSearch } = await import('../data/constitution/semantic-search');
  expect(await semanticSearch('presidential terms')).toEqual([]);
  expect(library.AutoModel.from_pretrained).not.toHaveBeenCalled();
  expect(extract).not.toHaveBeenCalled();
});

test.each([NaN, Infinity, -Infinity])('stored nonfinite value %s cannot become a score', async value => {
  assets(metadata(), vector(384, value).buffer);
  const { library } = await encoder();
  const { semanticSearch } = await import('../data/constitution/semantic-search');
  expect(await semanticSearch('presidential terms')).toEqual([]);
  expect(library.AutoModel.from_pretrained).not.toHaveBeenCalled();
});

test.each([0, 2, 3.4e38])('stored unnormalized vector %s is unavailable', async value => {
  assets(metadata(), vector(384, value).buffer);
  const { library } = await encoder();
  const { semanticSearch } = await import('../data/constitution/semantic-search');
  expect(await semanticSearch('presidential terms')).toEqual([]);
  expect(library.AutoModel.from_pretrained).not.toHaveBeenCalled();
});

test.each([0, 383, 385])('incorrect stored vector length %s is unavailable', async length => {
  assets(metadata(), vector(length).buffer);
  const { library } = await encoder();
  const { semanticSearch } = await import('../data/constitution/semantic-search');
  expect(await semanticSearch('presidential terms')).toEqual([]);
  expect(library.AutoModel.from_pretrained).not.toHaveBeenCalled();
});

test('length-compatible unsupported dimension is rejected before scoring', async () => {
  assets({ ...metadata(), dim: 383 }, vector(383).buffer);
  const { library } = await encoder();
  const { semanticSearch } = await import('../data/constitution/semantic-search');
  expect(await semanticSearch('presidential terms')).toEqual([]);
  expect(library.AutoModel.from_pretrained).not.toHaveBeenCalled();
});

test('duplicate article identities with correctly sized bytes are rejected', async () => {
  const meta = metadata();
  assets({ ...meta, count: 2, articles: [...meta.articles, ...meta.articles] },
    new Float32Array([...Array.from(vector()), ...Array.from(vector())]).buffer);
  const { library } = await encoder();
  const { semanticSearch } = await import('../data/constitution/semantic-search');
  expect(await semanticSearch('presidential terms')).toEqual([]);
  expect(library.AutoModel.from_pretrained).not.toHaveBeenCalled();
});

test('unaligned binary byte count is unavailable', async () => {
  assets(metadata(), new ArrayBuffer(1535));
  await encoder();
  const { semanticSearch } = await import('../data/constitution/semantic-search');
  expect(await semanticSearch('presidential terms')).toEqual([]);
});

const invalidQueries: [string, () => unknown][] = [
  ['null output', () => null], ['absent output', () => undefined],
  ['missing data', () => ({ dims: [1, 384] })],
  ['ordinary array', () => ({ data: Array.from(vector()), dims: [1, 384] })],
  ['Float64 data', () => ({ data: Float64Array.from(vector()), dims: [1, 384] })],
  ['short data', () => ({ data: vector(383), dims: [1, 384] })],
  ['long data', () => ({ data: vector(385), dims: [1, 384] })],
  ['missing dimensions', () => ({ data: vector() })],
  ['wrong dimensions', () => ({ data: vector(), dims: [384] })],
  ['transposed dimensions', () => ({ data: vector(), dims: [384, 1] })],
  ['string dimensions', () => ({ data: vector(), dims: ['1', '384'] })],
  ['NaN', () => ({ data: vector(384, NaN), dims: [1, 384] })],
  ['infinity', () => ({ data: vector(384, Infinity), dims: [1, 384] })],
  ['negative infinity', () => ({ data: vector(384, -Infinity), dims: [1, 384] })],
  ['zero vector', () => ({ data: vector(384, 0), dims: [1, 384] })],
  ['unnormalized', () => ({ data: vector(384, 2), dims: [1, 384] })],
];

test.each(invalidQueries)('invalid query output %s cannot reach scoring', async (_label, output) => {
  assets();
  await encoder(output());
  const { semanticSearch } = await import('../data/constitution/semantic-search');
  expect(await semanticSearch('presidential terms')).toEqual([]);
});

test('same hostile metadata/NaN fixture as the original caller report refuses', async () => {
  assets({ ...metadata(), model: 'unrelated/model', revision: 'other-revision' }, vector(384, NaN).buffer);
  const { library } = await encoder();
  const { semanticSearch } = await import('../data/constitution/semantic-search');
  expect(await semanticSearch('presidential terms')).toEqual([]);
  expect(library.AutoModel.from_pretrained).not.toHaveBeenCalled();
});

test('warm-up refuses a malformed asset and later valid search can reload', async () => {
  assets({ ...metadata(), revision: 'main' });
  const { library } = await encoder();
  const { semanticSearch, warmSemanticIndex } = await import('../data/constitution/semantic-search');
  await expect(warmSemanticIndex()).resolves.toBeUndefined();
  expect(library.AutoModel.from_pretrained).not.toHaveBeenCalled();
  expect(await semanticSearch('presidential terms')).toEqual([]);
  assets();
  expect((await semanticSearch('presidential terms'))[0].articleNumber).toBe(142);
});

test('query refusal does not poison an otherwise valid cached index', async () => {
  assets();
  const { library, extract } = await encoder();
  extract.mockResolvedValueOnce({ data: vector(383), dims: [1, 383] });
  const { semanticSearch } = await import('../data/constitution/semantic-search');
  expect(await semanticSearch('presidential terms')).toEqual([]);
  expect((await semanticSearch('presidential terms'))[0].articleNumber).toBe(142);
  expect(library.AutoModel.from_pretrained).toHaveBeenCalledTimes(1);
});
