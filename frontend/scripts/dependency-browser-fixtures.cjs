'use strict';

const modelPrefix = 'https://huggingface.co/Xenova/all-MiniLM-L6-v2/resolve/main/';
const modelFiles = ['config.json', 'tokenizer.json', 'tokenizer_config.json', 'onnx/model_quantized.onnx'];
const runtimeFiles = ['ort-wasm-simd-threaded.asyncify.mjs', 'ort-wasm-simd-threaded.asyncify.wasm'];

/**
 * Select only a complete approved HTTPS resource URL. The runtime version comes
 * from the installed locked package, never from the requested URL. Main-model
 * downloads are deliberately fulfilled with the verifier's pinned cache bytes.
 * @param {string} value Complete requested URL.
 * @param {string} runtimeVersion Exact installed ONNX Web version.
 * @returns {{kind: string, relative: string, contentType: string}|null} Fixture or refusal.
 */
function selectFixture(value, runtimeVersion) {
  if (typeof runtimeVersion !== 'string' || !/^\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?$/.test(runtimeVersion)) {
    throw new Error('Installed runtime version is unavailable');
  }
  for (const relative of modelFiles) {
    if (value === modelPrefix + relative) {
      return { kind: 'model', relative, contentType: relative.endsWith('.json') ? 'application/json' : 'application/octet-stream' };
    }
  }
  for (const relative of runtimeFiles) {
    for (const prefix of ['https://cdn.jsdelivr.net/npm/', 'https://unpkg.com/']) {
      if (value === `${prefix}onnxruntime-web@${runtimeVersion}/dist/${relative}`) {
        return { kind: 'runtime', relative, contentType: relative.endsWith('.wasm') ? 'application/wasm' : 'text/javascript' };
      }
    }
  }
  return null;
}

module.exports = { selectFixture };
