#!/usr/bin/env node
/**
 * Build-time embeddings for every Constitution article.
 *
 * Uses `@huggingface/transformers` (Xenova/all-MiniLM-L6-v2, 384-dim,
 * quantized ~23MB) to produce one mean-pooled, L2-normalised vector per
 * article. Vectors are written as a packed Float32 blob plus a small
 * index JSON that tells the runtime which vector maps to which article.
 *
 * Why build-time?
 *   • The model itself is small enough to ship to the browser (~23MB,
 *     cached after first load), but embedding 264 articles on every page
 *     load would be slow and cost the user bandwidth.
 *   • Pre-computing means the runtime only embeds the *query* (one short
 *     string) and does a dot product against cached article vectors.
 *
 * Run:
 *   node scripts/build-embeddings.mjs
 *
 * Outputs (under public/data/constitution/):
 *   embeddings.bin         — packed Float32 [N × 384]
 *   embeddings-index.json  — { model, dim, count, articles: [{ch, art, title}] }
 */
import { readFile, readdir, writeFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { env, pipeline } from '@huggingface/transformers';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const { prepareModel, configureLocalModel } = require('./embedding-model.cjs');
const { model: MODEL_ID, revision } = require('./embedding-model.json');

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, '..');
const DATA_DIR = resolve(ROOT, 'public/data/constitution');
const DIM = 384;

/**
 * Build the string we hand to the encoder. Mixing the title, summary,
 * explanation, paragraphs and tags gives the model enough context that
 * a colloquial query ("how many terms can a president serve?") lands
 * near Article 142 even though the article itself says "two terms".
 *
 * We keep it under ~1500 chars to stay inside the model's 512-token
 * context window without truncation.
 */
function buildDocText(chapter, article) {
  const parts = [
    `Chapter ${chapter.number}: ${chapter.title}`,
    `Article ${article.number}: ${article.title}`,
    article.summary ?? '',
    article.explanation ?? '',
    (article.tags ?? []).join(', '),
    article.paragraphs.join(' '),
  ].filter(Boolean);
  return parts.join('\n').slice(0, 1500);
}

async function loadAllChapters() {
  const files = (await readdir(DATA_DIR))
    .filter((f) => /^chapter-\d+\.json$/.test(f))
    .sort((a, b) => {
      const na = parseInt(a.match(/\d+/)[0], 10);
      const nb = parseInt(b.match(/\d+/)[0], 10);
      return na - nb;
    });
  const chapters = [];
  for (const f of files) {
    const body = await readFile(resolve(DATA_DIR, f), 'utf8');
    chapters.push(JSON.parse(body));
  }
  return chapters;
}

async function main() {
  console.log(`Loading chapters from ${DATA_DIR}…`);
  const chapters = await loadAllChapters();
  const rows = [];
  for (const ch of chapters) {
    for (const a of ch.articles) {
      rows.push({
        chapter: ch,
        article: a,
        text: buildDocText(ch, a),
      });
    }
  }
  console.log(`Encoding ${rows.length} articles with ${MODEL_ID}…`);

  const modelPath = await prepareModel(process.env.NATIVE_VERIFY_CACHE_DIR);
  configureLocalModel(env);
  console.log(JSON.stringify({ check: 'embedding-builder-input', model: MODEL_ID, revision, modelPath, device: 'cpu', allowRemoteModels: env.allowRemoteModels, useFSCache: env.useFSCache }));
  const extract = await pipeline('feature-extraction', modelPath, {
    device: 'cpu',
    local_files_only: true,
    dtype: 'q8', // quantized — same weights the browser will use
  });

  try {
    const flat = new Float32Array(rows.length * DIM);
    const index = [];
    let t0 = Date.now();
    for (let i = 0; i < rows.length; i++) {
      const row = rows[i];
      const out = await extract(row.text, { pooling: 'mean', normalize: true });
      assert.ok(out.data instanceof Float32Array && out.data.length === DIM, 'embedding output: expected 384 Float32 values');
      assert.deepEqual(out.dims, [1, DIM], 'embedding output: unexpected dimensions');
      assert.ok(out.data.every(Number.isFinite), 'embedding output: non-finite value');
      const norm = Math.sqrt(out.data.reduce((sum, value) => sum + value * value, 0));
      assert.ok(Math.abs(norm - 1) < 0.0001, 'embedding output: vector is not normalized');
      flat.set(out.data, i * DIM);
      index.push({
        ch: row.chapter.number,
        art: row.article.number,
        title: row.article.title,
      });
      if ((i + 1) % 20 === 0 || i === rows.length - 1) {
        const dt = ((Date.now() - t0) / 1000).toFixed(1);
        process.stdout.write(`  ${i + 1}/${rows.length}  (${dt}s)\r`);
      }
    }
    console.log('');

    const binPath = resolve(DATA_DIR, 'embeddings.bin');
    const idxPath = resolve(DATA_DIR, 'embeddings-index.json');
    await writeFile(binPath, Buffer.from(flat.buffer));
    await writeFile(
      idxPath,
      JSON.stringify(
        {
          model: MODEL_ID,
          dim: DIM,
          count: rows.length,
          articles: index,
        },
        null,
        2
      ) + '\n'
    );
    console.log(`Wrote ${binPath}  (${(flat.byteLength / 1024).toFixed(1)} KB)`);
    console.log(`Wrote ${idxPath}`);
  } finally {
    await extract.dispose();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
