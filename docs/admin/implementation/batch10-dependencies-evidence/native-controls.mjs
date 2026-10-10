import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { resolve, dirname } from 'node:path';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';

const local = createRequire(resolve(process.argv[2], 'package.json'));
const { env, pipeline } = await import(pathToFileURL(local.resolve('@huggingface/transformers')));
const caller = createRequire(local.resolve('@huggingface/transformers'));
const ort = caller('onnxruntime-node');
const varint = number => {
  const result = [];
  do { result.push((number & 127) | (number > 127 ? 128 : 0)); number >>>= 7; } while (number);
  return Buffer.from(result);
};
const integer = (field, value) => Buffer.concat([varint(field * 8), varint(value)]);
const message = (field, bytes) => Buffer.concat([varint(field * 8 + 2), varint(bytes.length), bytes]);
const text = (field, value) => message(field, Buffer.from(value));
const valueInfo = name => Buffer.concat([text(1, name), message(2, message(1, Buffer.concat([
  integer(1, 1), message(2, message(1, integer(1, 2))),
])))]);
const graph = Buffer.concat([message(1, Buffer.concat([text(1, 'x'), text(2, 'y'), text(4, 'Identity')])),
  text(2, 'batch10-dependencies-identity'), message(11, valueInfo('x')), message(12, valueInfo('y'))]);
const model = Buffer.concat([integer(1, 8), text(2, 'batch10-dependencies'), message(7, graph), message(8, integer(2, 13))]);
const session = await ort.InferenceSession.create(model, { executionProviders: ['cpu'] });
try {
  const output = await session.run({ x: new ort.Tensor('float32', new Float32Array([3, -4]), [2]) });
  assert.deepEqual([...output.y.data], [3, -4]);
  const binary = resolve(dirname(caller.resolve('onnxruntime-node')), '../bin/napi-v6', process.platform, process.arch, 'onnxruntime_binding.node');
  console.log(JSON.stringify({ check: 'actual-cpu-identity', output: [...output.y.data], platform: process.platform,
    arch: process.arch, runtime: ort.env.versions, binary, binary_sha256: createHash('sha256').update(await readFile(binary)).digest('hex') }));
} finally { await session.release(); }

env.cacheDir = process.env.NATIVE_VERIFY_CACHE_DIR;
env.allowLocalModels = true;
env.allowRemoteModels = false;
env.localModelPath = process.env.BATCH10_BUILDER_MODELS;
const extract = await pipeline('feature-extraction', 'Xenova/all-MiniLM-L6-v2', {
  dtype: 'q8', device: 'cpu', revision: '751bff37182d3f1213fa05d7196b954e230abad9',
});
try {
  const a = await extract('right to health care', { pooling: 'mean', normalize: true });
  const b = await extract('right to health care', { pooling: 'mean', normalize: true });
  assert.deepEqual(a.dims, [1, 384]);
  assert.equal(a.data.length, 384);
  assert.ok(a.data.every(Number.isFinite));
  assert.deepEqual(a.data, b.data);
  console.log(JSON.stringify({ check: 'fixed-model-repeatability', dimensions: a.dims,
    finite: true, identicalRepeatedOutput: true, modelRevision: '751bff37182d3f1213fa05d7196b954e230abad9' }));
} finally { await extract.dispose(); }
