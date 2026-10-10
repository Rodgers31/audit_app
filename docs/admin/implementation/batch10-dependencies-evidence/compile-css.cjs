'use strict';

const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { createRequire } = require('node:module');

async function main() {
  const [directory, destination] = process.argv.slice(2);
  const root = path.resolve(directory);
  process.chdir(root);
  const local = createRequire(path.join(root, 'package.json'));
  const config = local('./postcss.config.js');
  const source = path.join(root, 'app/globals.css');
  const plugins = Object.entries(config.plugins).map(([name, options]) => local(name)(options));
  const result = await local('postcss')(plugins).process(fs.readFileSync(source), { from: source });
  fs.writeFileSync(destination, result.css, { flag: 'wx' });
  console.log(JSON.stringify({ check: 'actual-app-css', root,
    tailwind: local('tailwindcss/package.json').version,
    bytes: Buffer.byteLength(result.css), css_sha256: crypto.createHash('sha256').update(result.css).digest('hex'),
    destination, warnings: result.warnings().map(String) }));
}

main().catch(error => { console.error(error); process.exitCode = 1; });
