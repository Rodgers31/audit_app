'use strict';

// Run against an npm ci --omit=dev installation or the pruned container runner.
// This checks installed exposure, not advisory status or deployed readiness.
const assert = require('node:assert/strict');
const { createRequire } = require('node:module');
const fs = require('node:fs');
const path = require('node:path');

const excludedPackages = new Set([
  'tailwindcss', 'autoprefixer', 'braces', 'micromatch', 'chokidar',
  '@huggingface/transformers', 'onnxruntime-node', 'onnxruntime-web',
  'onnxruntime-common', '@huggingface/jinja', '@huggingface/tokenizers',
  '@tailwindcss/typography', 'adm-zip', 'sprintf-js', 'jest', 'eslint',
]);

function inspectInstalledPackages(directory, seen = new Set()) {
  const real = fs.realpathSync(directory);
  if (seen.has(real)) return 0;
  seen.add(real);
  let count = 0;
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    if (entry.name.startsWith('.') || entry.isFile()) continue;
    const packagePath = path.join(directory, entry.name);
    if (entry.name.startsWith('@')) {
      count += inspectInstalledPackages(packagePath, seen);
      continue;
    }
    const metadata = JSON.parse(fs.readFileSync(path.join(packagePath, 'package.json'), 'utf8'));
    assert.equal(typeof metadata.name, 'string', 'Installed package identity is missing');
    assert.ok(!excludedPackages.has(metadata.name), `${metadata.name} must be absent from the pruned runtime (${packagePath})`);
    count++;
    const nested = path.join(packagePath, 'node_modules');
    if (fs.existsSync(nested)) count += inspectInstalledPackages(nested, seen);
  }
  return count;
}

async function main() {
  const root = path.resolve(process.argv[2] || path.join(__dirname, '..'));
  const runtimeRequire = createRequire(path.join(root, 'package.json'));
  const manifest = runtimeRequire('./package.json');
  assert.equal(manifest.name, 'audit-app-frontend');
  for (const key of ['dependencies', 'devDependencies']) {
    assert.ok(manifest[key] && typeof manifest[key] === 'object' && !Array.isArray(manifest[key]), `${key} must be a dependency map`);
  }
  const installedPackageCount = inspectInstalledPackages(path.join(root, 'node_modules'));
  assert.ok(installedPackageCount > 0, 'Installed runtime packages are missing');
  for (const name of excludedPackages) {
    assert.throws(() => runtimeRequire.resolve(name), { code: 'MODULE_NOT_FOUND' },
      `${name} must be absent from the pruned runtime`);
  }
  for (const name of ['next', 'react', 'react-dom', 'axios']) runtimeRequire.resolve(name);
  const nextRequire = createRequire(runtimeRequire.resolve('next/package.json'));
  const sharp = nextRequire('sharp');
  const png = await sharp({ create: { width: 2, height: 2, channels: 3, background: '#ff0000' } }).png().toBuffer();
  const webp = await sharp(png).resize(1, 1).webp().toBuffer();
  const metadata = await sharp(webp).metadata();
  assert.equal(metadata.width, 1);
  assert.equal(metadata.height, 1);
  assert.equal(metadata.format, 'webp');
  console.log(JSON.stringify({ check: 'pruned-runtime-dependencies', root, node: process.version,
    platform: process.platform, arch: process.arch, next: nextRequire('./package.json').version,
    sharp: sharp.versions.sharp, imageDecode: true, installedPackageCount,
    excludedPackageNames: [...excludedPackages], excludedPackagesAbsent: true }));
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
