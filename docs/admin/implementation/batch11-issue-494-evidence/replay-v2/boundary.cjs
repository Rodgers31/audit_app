'use strict';
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path');
const crypto = require('node:crypto');
const hash = p => crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
function realPath(input) {
 assert.ok(typeof input === 'string' && path.isAbsolute(input) && !input.split(path.sep).includes('..'), 'absolute non-traversing path required');
 let current = path.parse(input).root;
 for (const part of input.slice(current.length).split(path.sep).filter(Boolean)) {
  current = path.join(current, part);
  let stat;
  try { stat = fs.lstatSync(current); } catch (error) { if (error.code !== 'ENOENT') throw error; continue; }
  assert.ok(!stat.isSymbolicLink(), 'symlink ancestor refused');
 }
 return path.resolve(input);
}
function sourceFile(root, name) {
 assert.ok(name && !path.isAbsolute(name) && !name.includes('\\') && name.split('/').every(p => p && p !== '.' && p !== '..'), 'unsafe source member');
 const target = realPath(path.join(root, name));
 assert.ok(fs.lstatSync(target).isFile(), 'regular source member required');
 return target;
}
function externalFresh(root, input) {
 const target = realPath(input);
 assert.ok(target !== root && !target.startsWith(root + path.sep) && !root.startsWith(target + path.sep), 'external output required');
 assert.ok(!fs.existsSync(target), 'fresh output required');
 assert.ok(fs.lstatSync(path.dirname(target)).isDirectory(), 'real output parent required');
 return target;
}
function environment(scratch) {
 const env = {PATH:[path.dirname(process.execPath), '/usr/bin', '/bin'].join(path.delimiter), LANG:'C.UTF-8',
  HOME:path.join(scratch, 'home'), TMPDIR:path.join(scratch, 'tmp'), PYTHON_DOTENV_DISABLED:'1',
  NEXT_TELEMETRY_DISABLED:'1', ONNXRUNTIME_NODE_INSTALL:'skip', npm_config_engine_strict:'true',
  npm_config_userconfig:path.join(scratch, 'npm-user'), npm_config_globalconfig:path.join(scratch, 'npm-global'),
  npm_config_cache:path.join(scratch, 'npm-cache')};
 for (const key of ['HOME', 'TMPDIR', 'npm_config_cache']) fs.mkdirSync(env[key]);
 for (const key of ['npm_config_userconfig', 'npm_config_globalconfig']) fs.writeFileSync(env[key], '', {flag:'wx'});
 return env;
}
function sourceInventory(root) {
 const files = {};
 function walk(relative) {
  for (const name of fs.readdirSync(path.join(root, relative)).sort()) {
   if (relative === '' && ['node_modules', '.next', '.git'].includes(name)) continue;
   assert.ok(!name.startsWith('.env') || /\.(example|sample|template)$/.test(name), 'runtime dotenv refused');
   const nameRelative = relative ? `${relative}/${name}` : name;
   const target = realPath(path.join(root, nameRelative)), stat = fs.lstatSync(target);
   if (stat.isDirectory()) walk(nameRelative);
   else { assert.ok(stat.isFile(), 'regular source member required'); files[nameRelative] = hash(target); }
  }
 }
 walk(''); assert.ok(Object.keys(files).length, 'nonempty source required'); return files;
}
module.exports = {realPath, sourceFile, externalFresh, environment, sourceInventory, hash};
