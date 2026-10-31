'use strict';
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { createRequire } = require('node:module');
const front = '/Users/roger/.codex/worktrees/dependency-security-weekly/audit_app/frontend';
const owned = createRequire(path.join(front, 'package.json'));
const { ESLint } = owned('eslint');
const glob = createRequire(owned.resolve('tailwindcss/package.json'))('fast-glob');
const hash = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
(async () => {
  const files = glob.sync('{pages,components,lib,src,app}/**/*.{js,jsx,ts,tsx,mjs,cjs}', { cwd: front, absolute: true, onlyFiles: true, dot: true }).sort();
  for (const ext of ['js', 'jsx', 'ts', 'tsx', 'mjs', 'cjs']) files.push(path.join(front, '__standards_effective_probe__.' + ext));
  const engine = new ESLint({ cwd: front });
  const configs = {}, paths = {}, ignored = [];
  for (const file of files) {
    const relative = path.relative(front, file);
    if (!relative.startsWith('__standards_effective_probe__') && await engine.isPathIgnored(file)) { ignored.push(relative); continue; }
    const effective = await engine.calculateConfigForFile(file);
    const normalized = JSON.parse(JSON.stringify(effective).split(front).join('<frontend>'));
    const digest = hash(JSON.stringify(normalized));
    configs[digest] = normalized; paths[relative] = digest;
  }
  const sourceInputs = {};
  for (const relative of ['package.json', 'package-lock.json', '.eslintrc.json', ...glob.sync('eslint-rules/**/*', { cwd: front, onlyFiles: true, dot: true }).sort()]) sourceInputs[relative] = hash(fs.readFileSync(path.join(front, relative)));
  const result = { at: new Date().toISOString(), frontend: front, sourceInputs, filesChecked: Object.keys(paths).length, ignored, configs, paths };
  fs.writeFileSync(path.join(__dirname, 'baseline-effective-configs.json'), JSON.stringify(result, null, 2) + '\n', { flag: 'wx' });
  console.log(JSON.stringify({ filesChecked: result.filesChecked, uniqueConfigs: Object.keys(configs).length, ignored: ignored.length, sourceInputs }));
})().catch(error => { console.error(error); process.exitCode = 1; });
