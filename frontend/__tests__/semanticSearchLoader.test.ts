import manifest from '../scripts/embedding-model.json';

jest.mock('../scripts/embedding-model.json', () => ({
  ...jest.requireActual('../scripts/embedding-model.json'),
  revision: 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
}));
jest.mock('@huggingface/transformers', () => ({
  BertTokenizer: jest.fn(),
  AutoModel: { from_pretrained: jest.fn().mockResolvedValue({}) },
  FeatureExtractionPipeline: jest.fn().mockImplementation(() => async () => {
    const data = new Float32Array(384);
    data[0] = 1;
    return { data, dims: [1, 384] };
  }),
}));

const originalFetch = global.fetch;
const originalTimeout = AbortSignal.timeout;

beforeEach(() => {
  jest.resetModules();
  Object.defineProperty(AbortSignal, 'timeout', {
    configurable: true, value: () => new AbortController().signal,
  });
});
afterEach(() => {
  global.fetch = originalFetch;
  Object.defineProperty(AbortSignal, 'timeout', { configurable: true, value: originalTimeout });
});

function assets(failedTokenizer = false) {
  const vector = new Float32Array(384);
  vector[0] = 1;
  global.fetch = jest.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith('embeddings.bin')) return { ok: true, arrayBuffer: async () => vector.buffer } as Response;
    if (url.endsWith('embeddings-index.json')) return { ok: true, json: async () => ({
      model: manifest.model, dim: 384, count: 1, articles: [{ ch: 9, art: 142, title: 'Term of President' }],
    }) } as Response;
    return { ok: !failedTokenizer, json: async () => ({}) } as Response;
  });
}

test('browser loader uses shared revision for tokenizer and model with a valid ranking', async () => {
  assets();
  const { semanticSearch } = await import('../data/constitution/semantic-search');
  const { AutoModel, BertTokenizer, FeatureExtractionPipeline } = await import('@huggingface/transformers');
  expect(await semanticSearch('presidential terms')).toEqual([{ chapterNumber: 9, articleNumber: 142, score: 1 }]);
  expect(AutoModel.from_pretrained).toHaveBeenCalledWith(manifest.model, { dtype: 'q8', revision: manifest.revision });
  const urls = (global.fetch as jest.Mock).mock.calls.map(([url]) => String(url)).filter(url => url.startsWith('https:'));
  expect(urls.sort()).toEqual(['tokenizer.json', 'tokenizer_config.json'].map(file =>
    `https://huggingface.co/${manifest.model}/resolve/${manifest.revision}/${file}`).sort());
  expect(BertTokenizer).toHaveBeenCalledTimes(1);
  expect(FeatureExtractionPipeline).toHaveBeenCalledTimes(1);
});

test('failed pinned tokenizer returns the existing unavailable result before loading a model', async () => {
  assets(true);
  const { semanticSearch } = await import('../data/constitution/semantic-search');
  const { AutoModel } = await import('@huggingface/transformers');
  expect(await semanticSearch('presidential terms')).toEqual([]);
  expect(AutoModel.from_pretrained).not.toHaveBeenCalled();
});

test('model-load refusal returns the existing unavailable result', async () => {
  assets();
  const { semanticSearch } = await import('../data/constitution/semantic-search');
  const { AutoModel } = await import('@huggingface/transformers');
  (AutoModel.from_pretrained as jest.Mock).mockRejectedValueOnce(new Error('controlled model refusal'));
  expect(await semanticSearch('presidential terms')).toEqual([]);
});
