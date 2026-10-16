'use strict';
const assert = require('node:assert/strict');
const { test } = require('node:test');
const { createRequire } = require('node:module');
const app = createRequire(require.resolve('../package.json'));
const deep = '{'.repeat(4000) + 'a,b' + '}'.repeat(4000);
for (const name of ['tailwindcss', '@next/eslint-plugin-next']) {
 const caller = createRequire(app.resolve(`${name}/package.json`));
 const fast = createRequire(caller.resolve('fast-glob/package.json'));
 const micro = createRequire(fast.resolve('micromatch/package.json'));
 const braces = micro('braces');
 test(`${name}: actual fast-glob rejects nested input before recursion`, () => {
  assert.throws(() => caller('fast-glob').sync(deep), e => e.code === 'ERR_BRACES_DEPTH');
 });
 for (const method of ['parse', 'compile', 'expand', 'stringify']) {
  test(`${name}: ${method} bounds nested pattern`, () => {
   assert.throws(() => braces[method](deep), e => e.code === 'ERR_BRACES_DEPTH');
  });
 }
 test(`${name}: nesting boundary cannot be relaxed by caller options`, () => {
  assert.ok(braces.parse('{'.repeat(64) + 'a,b' + '}'.repeat(64)));
  for (const options of [{}, { maxDepth: Infinity }, { maxDepth: false }, { maxLength: Infinity }]) {
   assert.throws(() => braces.parse('{'.repeat(65) + 'a,b' + '}'.repeat(65), options), e => e.code === 'ERR_BRACES_DEPTH');
  }
  assert.throws(() => braces.parse('('.repeat(65) + 'text' + ')'.repeat(65)), e => e.code === 'ERR_BRACES_DEPTH');
 });
 for (const method of ['compile', 'stringify', 'expand']) {
  test(`${name}: direct ${method} AST walkers bound deep or cyclic nodes`, () => {
   const ast = { type: 'root', nodes: [] }; let node = ast;
   for (let i = 0; i < 140; i++) { const child = { type: 'brace', nodes: [], parent: node, open: true, close: true, commas: 1 }; node.nodes.push(child); node = child; }
   assert.throws(() => braces[method](ast), e => e.code === 'ERR_BRACES_DEPTH');
   const cyclic = { type: 'root', nodes: [] }; cyclic.nodes.push(cyclic);
   assert.throws(() => braces[method](cyclic), e => e.code === 'ERR_BRACES_DEPTH');
  });
 }
 test(`${name}: shallow braces keep expansion and compile semantics`, () => {
  assert.deepEqual(braces.expand('x/{a,b}/{1..3}'), ['x/a/1', 'x/a/2', 'x/a/3', 'x/b/1', 'x/b/2', 'x/b/3']);
  assert.equal(braces.compile('x/{a,b}'), 'x/(a|b)');
  assert.equal(braces.stringify('x/{a,b}'), 'x/{a,b}');
 });
 test(`${name}: escaped, quoted, bracket and sibling braces keep semantics`, () => {
  for (const input of ['\\{a,b\\}', '"{a,b}"', '[{a,b}]', '{a,b}{c,d}']) {
   assert.ok(braces.expand(input).length > 0);
  }
 });
}
test('direct expansion bounds nested queue values as well as AST nodes', () => {
 const braces = require('braces'); let value = 'x';
 for (let i = 0; i < 8000; i++) value = [value];
 assert.throws(() => braces.expand({ type: 'root', nodes: [{ type: 'text', value }] }), e => e.code === 'ERR_BRACES_DEPTH');
});
test('the reviewed lock and installed tree contain argparse2 without sprintf-js', () => {
 const fs = require('node:fs');
 const lock = JSON.parse(fs.readFileSync(require.resolve('../package-lock.json')));
 assert.ok(!Object.keys(lock.packages).some(p => /(?:^|\/)node_modules\/sprintf-js$/.test(p)));
 assert.equal(require('argparse/package.json').version, '2.0.1');
 assert.throws(() => app.resolve('sprintf-js'), { code: 'MODULE_NOT_FOUND' });
});
