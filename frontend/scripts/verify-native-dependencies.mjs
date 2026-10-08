#!/usr/bin/env node
/**
 * Exercise the native dependencies used by the offline embedding builder and
 * Next image optimization. This downloads the app's public q8 model (~23 MB)
 * into a temporary cache; it never rewrites the shipped embeddings.
 *
 * Run: NATIVE_VERIFY_CACHE_DIR=/path/to/cache node scripts/verify-native-dependencies.mjs
 * This verifies Node CPU inference, not browser WASM inference.
 */
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { env, pipeline, RawImage } from '@huggingface/transformers';

const require = createRequire(import.meta.url);
const transformersRequire = createRequire(require.resolve('@huggingface/transformers'));
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const dataDir = resolve(root, 'public/data/constitution');
const model = 'Xenova/all-MiniLM-L6-v2';
// Pin the public model revision so repeat runs verify the same weights.
const revision = '751bff37182d3f1213fa05d7196b954e230abad9';
env.cacheDir = resolve(process.env.NATIVE_VERIFY_CACHE_DIR || resolve(tmpdir(), 'audit-app-native-model-cache'));
env.allowLocalModels = false;

function dot(a, b) {
  return a.reduce((sum, value, i) => sum + value * b[i], 0);
}

function checkVector(output) {
  assert.ok(output.data instanceof Float32Array, 'Embedding data must remain Float32Array');
  assert.deepEqual(output.dims, [1, 384], 'Mean pooling must retain the 384-dimensional contract');
  assert.equal(output.data.length, 384);
  assert.ok(output.data.every(Number.isFinite), 'Embedding contains non-finite values');
  const norm = Math.sqrt(dot(output.data, output.data));
  assert.ok(Math.abs(norm - 1) < 0.0001, `Embedding is not normalized: ${norm}`);
  return output.data;
}

async function checkImages(caller, callerRequire) {
  const sharp = callerRequire('sharp');
  const svg = Buffer.from('<svg xmlns="http://www.w3.org/2000/svg" width="2" height="2"><rect width="2" height="2" fill="#ff0000"/></svg>');
  // SVG exercises librsvg; PNG exercises the normal native decode path.
  const png = await sharp(svg).removeAlpha().png().toBuffer();
  const decoded = await sharp(png).removeAlpha().raw().toBuffer({ resolveWithObject: true });
  assert.equal(decoded.info.width, 2);
  assert.equal(decoded.info.height, 2);
  assert.equal(decoded.info.channels, 3);
  assert.deepEqual([...decoded.data], Array.from({ length: 4 }, () => [255, 0, 0]).flat());
  const resized = await sharp(png).resize(1, 1).webp().toBuffer();
  const metadata = await sharp(resized).metadata();
  assert.equal(metadata.width, 1);
  assert.equal(metadata.height, 1);
  assert.equal(metadata.format, 'webp');
  console.log(JSON.stringify({ check: 'native-image-decode', caller, sharp: sharp.versions.sharp, vips: sharp.versions.vips, svg: true, png: true, webp: true }));
  return png;
}

async function checkInstallerZip() {
  const runtimeRequire = createRequire(transformersRequire.resolve('onnxruntime-node'));
  const AdmZip = runtimeRequire('adm-zip');
  const entryName = 'runtimes/linux-x64/native/verification.txt';
  const contents = Buffer.from('Public native dependency verification fixture\n');
  const fixture = new AdmZip();
  fixture.addFile(entryName, contents);
  const archive = new AdmZip(fixture.toBuffer());
  // These are the lookup/extraction APIs used by ORT's NuGet installer.
  const entry = archive.getEntry(entryName);
  assert.ok(entry);
  assert.deepEqual(entry.getData(), contents);
  const temporary = await mkdtemp(resolve(tmpdir(), 'audit-app-zip-verify-'));
  try {
    archive.extractEntryTo(entry, temporary, false, true);
    assert.deepEqual(await readFile(resolve(temporary, 'verification.txt')), contents);
  } finally {
    await rm(temporary, { recursive: true, force: true });
  }
  console.log(JSON.stringify({ check: 'installer-zip-extraction', admZip: runtimeRequire('adm-zip/package.json').version, entry: entryName }));
}

async function main() {
  console.log(JSON.stringify({ check: 'environment', node: process.version, platform: process.platform, arch: process.arch, transformers: env.version, onnxruntime: transformersRequire('onnxruntime-node').env.versions, model, revision, cacheDir: env.cacheDir }));
  await checkInstallerZip();
  const png = await checkImages('transformers', transformersRequire);
  await checkImages('next', createRequire(require.resolve('next/package.json')));
  // Also pass the image through Transformers' actual Sharp adapter.
  const image = await RawImage.fromBlob(new Blob([png], { type: 'image/png' }));
  assert.equal(image.width, 2);
  assert.equal(image.height, 2);
  assert.equal(image.channels, 3);
  assert.deepEqual([...image.data], Array.from({ length: 4 }, () => [255, 0, 0]).flat());

  const index = JSON.parse(await readFile(resolve(dataDir, 'embeddings-index.json'), 'utf8'));
  assert.equal(index.model, model);
  assert.equal(index.dim, 384);
  assert.equal(index.count, index.articles.length);
  const binary = await readFile(resolve(dataDir, 'embeddings.bin'));
  assert.equal(binary.length, index.count * index.dim * Float32Array.BYTES_PER_ELEMENT);
  const vectors = new Float32Array(binary.buffer.slice(binary.byteOffset, binary.byteOffset + binary.byteLength));
  const articlePosition = index.articles.findIndex((entry) => entry.ch === 9 && entry.art === 142);
  assert.ok(articlePosition >= 0, 'Committed Article 142 embedding is missing');
  const chapter = JSON.parse(await readFile(resolve(dataDir, 'chapter-9.json'), 'utf8'));
  const article = chapter.articles.find((entry) => entry.number === 142);
  assert.ok(article, 'Article 142 source text is missing');
  // Use the offline builder's input format without invoking its file writes.
  const articleText = [
    `Chapter ${chapter.number}: ${chapter.title}`,
    `Article ${article.number}: ${article.title}`,
    article.summary ?? '',
    article.explanation ?? '',
    (article.tags ?? []).join(', '),
    article.paragraphs.join(' '),
  ].filter(Boolean).join('\n').slice(0, 1500);

  console.log('Loading the fixed public model for native CPU inference…');
  const extract = await pipeline('feature-extraction', model, { dtype: 'q8', device: 'cpu', revision });
  try {
    const articleVector = checkVector(await extract(articleText, { pooling: 'mean', normalize: true }));
    const committedVector = vectors.subarray(articlePosition * index.dim, (articlePosition + 1) * index.dim);
    const compatibility = dot(articleVector, committedVector) / Math.sqrt(dot(committedVector, committedVector));
    // Baseline Linux x64 q8 inference has shipped-index cosines 0.9945–0.9968
    // across five representative articles; ARM native results differ too.
    // This 0.99 floor checks semantic compatibility for this article. It is
    // neither a bit-exact output check nor a guarantee for the whole index.
    assert.ok(compatibility > 0.99, `Embedding differs substantially from the shipped index: cosine ${compatibility}`);
    const query = 'how many terms can a president serve?';
    const queryVector = checkVector(await extract(query, { pooling: 'mean', normalize: true }));
    const top = index.articles.map((entry, i) => ({
      chapterNumber: entry.ch,
      articleNumber: entry.art,
      score: dot(queryVector, vectors.subarray(i * index.dim, (i + 1) * index.dim)),
    })).sort((a, b) => b.score - a.score).slice(0, 5);
    assert.equal(top[0]?.articleNumber, 142, `Article 142 must rank first: ${JSON.stringify(top)}`);
    console.log(JSON.stringify({ check: 'native-model-inference', dimensions: 384, article: 142, committedIndexCosine: compatibility, compatibilityFloor: 0.99, query, top }));
  } finally {
    await extract.dispose();
  }
  console.log('Native dependency verification passed (Node CPU and image decode).');
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
