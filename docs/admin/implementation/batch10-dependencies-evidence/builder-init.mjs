import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';

const local = createRequire(resolve(process.env.BATCH10_BUILDER_ROOT, 'package.json'));
const { env } = await import(pathToFileURL(local.resolve('@huggingface/transformers')));
env.localModelPath = process.env.BATCH10_BUILDER_MODELS;
env.allowLocalModels = true;
env.allowRemoteModels = false;
env.cacheDir = process.env.NATIVE_VERIFY_CACHE_DIR;
console.log(JSON.stringify({ check: 'builder-owned-model-configuration', localModelPath: env.localModelPath,
  allowRemoteModels: env.allowRemoteModels, allowLocalModels: env.allowLocalModels, cacheDir: env.cacheDir }));
