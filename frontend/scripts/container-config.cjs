const fs = require('node:fs');
const path = require('node:path');
const { validateHttpBaseUrl, validatePublicConfig } = require('../lib/config/public-config.cjs');
const marker = path.resolve('.next/public-build-config.json');

function validateRuntime(env, baked) {
  if (baked?.version !== 1 || !baked.publicConfig) throw new Error('Frontend public build configuration marker is missing or invalid');
  const current = validatePublicConfig(env);
  for (const name of Object.keys(current)) {
    if (current[name] !== baked.publicConfig[name]) {
      throw new Error(`${name} differs from the baked frontend configuration; rebuild the image with matching public values`);
    }
  }
  // The internal transport is runtime-only and may differ between deployments.
  if (env.INTERNAL_API_URL !== undefined) validateHttpBaseUrl(env.INTERNAL_API_URL, 'INTERNAL_API_URL');
  return current;
}

function run(command) {
  if (command === 'validate') validatePublicConfig(process.env);
  else if (command === 'record') {
    fs.writeFileSync(marker, JSON.stringify({ version: 1, publicConfig: validatePublicConfig(process.env) }, null, 2) + '\n');
  } else if (command === 'runtime') {
    let baked;
    try { baked = JSON.parse(fs.readFileSync(marker, 'utf8')); } catch { throw new Error('Frontend public build configuration marker is missing or invalid'); }
    validateRuntime(process.env, baked);
  } else throw new Error('Usage: node scripts/container-config.cjs validate|record|runtime');
}

if (require.main === module) {
  try { run(process.argv[2]); } catch (error) { console.error(`Frontend configuration error: ${error.message}`); process.exitCode = 1; }
}
module.exports = { validateRuntime };
