'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { test } = require('node:test');

// These doubles test output admission, not native inference. The separate
// verify:native entry and actual 264-article builder replay exercise real ORT.
for (const [mode, accepted, diagnostic] of [
  ['valid', true, null], ['short', false, /expected 384 Float32/],
  ['NaN', false, /non-finite/], ['infinity', false, /non-finite/],
  ['array', false, /expected 384 Float32/], ['dimensions', false, /unexpected dimensions/],
  ['zero', false, /not normalized/],
]) {
  test(`embedding builder ${accepted ? 'accepts' : 'refuses'} ${mode} output before writing`, () => {
    const root = fs.mkdtempSync(path.join(fs.realpathSync(os.tmpdir()), 'batch12-dependencies-builder-'));
    try {
      const scripts = path.join(root, 'scripts'); fs.mkdirSync(scripts);
      fs.copyFileSync(path.join(__dirname, 'build-embeddings.mjs'), path.join(scripts, 'build-embeddings.mjs'));
      fs.copyFileSync(path.join(__dirname, 'embedding-model.json'), path.join(scripts, 'embedding-model.json'));
      fs.writeFileSync(path.join(scripts, 'embedding-model.cjs'), 'exports.prepareModel=async()=>"owned-output-fixture"; exports.configureLocalModel=()=>{};');
      const mod = path.join(root, 'node_modules/@huggingface/transformers'); fs.mkdirSync(mod, { recursive: true });
      fs.writeFileSync(path.join(mod, 'package.json'), JSON.stringify({ type: 'module', exports: './index.js' }));
      fs.writeFileSync(path.join(mod, 'index.js'), `
        export const env = {};
        export async function pipeline() {
          const extract = async () => {
            const data = new Float32Array(${mode === 'short' ? 383 : 384}); data[0] = 1;
            if (${JSON.stringify(mode)} === 'NaN') data[0] = NaN;
            if (${JSON.stringify(mode)} === 'infinity') data[0] = Infinity;
            if (${JSON.stringify(mode)} === 'zero') data.fill(0);
            return { data: ${mode === 'array' ? '[...data]' : 'data'}, dims: [1, ${mode === 'dimensions' ? 383 : 384}] };
          };
          extract.dispose = async () => console.log('owned pipeline disposed'); return extract;
        }
      `);
      const data = path.join(root, 'public/data/constitution'); fs.mkdirSync(data, { recursive: true });
      fs.writeFileSync(path.join(data, 'chapter-1.json'), JSON.stringify({ number: 1, title: 'Fixture', articles: [{ number: 1, title: 'Fixture', paragraphs: ['Fixture'] }] }));
      for (const name of ['embeddings.bin', 'embeddings-index.json']) fs.writeFileSync(path.join(data, name), 'retained output');
      const result = spawnSync(process.execPath, [path.join(scripts, 'build-embeddings.mjs')], {
        cwd: root, encoding: 'utf8', timeout: 10000, env: { PATH: process.env.PATH },
      });
      assert.equal(result.signal, null, result.stderr);
      assert.equal(result.status, accepted ? 0 : 1, result.stderr);
      if (accepted) {
        assert.equal(fs.readFileSync(path.join(data, 'embeddings.bin')).length, 384 * 4);
        assert.equal(JSON.parse(fs.readFileSync(path.join(data, 'embeddings-index.json'))).count, 1);
      } else {
        assert.match(result.stderr, diagnostic);
        assert.match(result.stdout, /owned pipeline disposed/);
        for (const name of ['embeddings.bin', 'embeddings-index.json']) assert.equal(fs.readFileSync(path.join(data, name), 'utf8'), 'retained output');
      }
    } finally { fs.rmSync(root, { recursive: true, force: true }); }
  });
}
