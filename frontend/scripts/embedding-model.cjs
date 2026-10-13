'use strict';

const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { createHash } = require('node:crypto');
const manifest = require('./embedding-model.json');

function refuse(message) {
  throw Object.assign(new Error(`embedding model input: ${message}`), { code: 'ERR_EMBEDDING_MODEL_INPUT' });
}

/** Verify an approved public artifact before JSON parsing or native model loading. */
function verifyModelBytes(relative, bytes) {
  const expected = Object.hasOwn(manifest.files, relative) && manifest.files[relative];
  if (!expected || !Buffer.isBuffer(bytes)) refuse('unapproved artifact or byte type');
  if (bytes.length !== expected.bytes || createHash('sha256').update(bytes).digest('hex') !== expected.sha256) {
    refuse(`unreviewed bytes for ${relative}`);
  }
}

function inspect(directory, prefix = '') {
  let stat;
  try { stat = fs.lstatSync(directory); } catch (error) { if (error.code === 'ENOENT') return; throw error; }
  if (!stat.isDirectory() || stat.isSymbolicLink()) refuse('model directory must be a real directory');
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const relative = prefix + entry.name;
    const filename = path.join(directory, entry.name);
    if (entry.isDirectory() && relative === 'onnx') inspect(filename, 'onnx/');
    else if (!entry.isFile() || !Object.hasOwn(manifest.files, relative)) refuse(`unexpected model entry ${relative}`);
    else {
      if (fs.statSync(filename).size !== manifest.files[relative].bytes) refuse(`unreviewed size for ${relative}`);
      verifyModelBytes(relative, fs.readFileSync(filename));
    }
  }
}

function checkAncestors(directory) {
  for (let current = directory; current !== path.dirname(current); current = path.dirname(current)) {
    try {
      const stat = fs.lstatSync(current);
      if (stat.isSymbolicLink() || !stat.isDirectory()) refuse('cache ancestry must contain real directories');
    } catch (error) { if (error.code !== 'ENOENT') throw error; }
  }
}

/**
 * Download missing fixed-revision files from the model publisher, with exact
 * size/hash checks and a finite deadline. Refuse changed retained files; never
 * refresh them silently. The cache is trusted against concurrent local writers.
 */
async function prepareModel(cache = path.join(fs.realpathSync(os.tmpdir()), 'audit-app-native-model-cache')) {
  if (typeof cache !== 'string' || !path.isAbsolute(cache)) refuse('cache must be an absolute path');
  const modelPath = path.join(path.resolve(cache), manifest.model, manifest.revision);
  checkAncestors(modelPath);
  inspect(modelPath);
  for (const [relative, expected] of Object.entries(manifest.files)) {
    const filename = path.join(modelPath, relative);
    if (fs.existsSync(filename)) continue;
    const response = await fetch(`https://huggingface.co/${manifest.model}/resolve/${manifest.revision}/${relative}`, {
      signal: AbortSignal.timeout(60000),
    });
    if (response.status !== 200 || !response.body) refuse(`download failed for ${relative}`);
    const chunks = [];
    let size = 0;
    for await (const chunk of response.body) {
      size += chunk.length;
      if (size > expected.bytes) refuse(`oversized download for ${relative}`);
      chunks.push(chunk);
    }
    const bytes = Buffer.concat(chunks);
    verifyModelBytes(relative, bytes);
    fs.mkdirSync(path.dirname(filename), { recursive: true });
    fs.writeFileSync(filename, bytes, { flag: 'wx' });
    verifyModelBytes(relative, fs.readFileSync(filename));
  }
  inspect(modelPath);
  return modelPath;
}

/** Use the checked snapshot exclusively; library defaults/caches cannot replace it. */
function configureLocalModel(env) {
  env.allowLocalModels = true;
  env.allowRemoteModels = false;
  env.useFSCache = false;
  env.useBrowserCache = false;
  env.useCustomCache = false;
}

module.exports = { prepareModel, verifyModelBytes, configureLocalModel };
