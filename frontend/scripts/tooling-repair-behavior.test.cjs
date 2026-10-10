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
const nyc = createRequire(app.resolve('@istanbuljs/load-nyc-config/package.json'));
const yaml = createRequire(nyc.resolve('js-yaml/package.json'));
const argparse = createRequire(yaml.resolve('argparse/package.json'));
const { sprintf, vsprintf } = argparse('sprintf-js');
for (const [name, fn] of [['sprintf', f => sprintf(f, 1)], ['vsprintf', f => vsprintf(f, [1])],
 ['format', f => sprintf.format(sprintf.parse(f), [f, 1])]]) {
 for (const f of ['%.101f', '%.101e', '%.101g', '%.999999999999999999999999f']) {
  test(`argparse ${name}: rejects ${f} before native numeric formatting`, () => {
   assert.throws(() => fn(f), e => e.code === 'ERR_SPRINTF_PRECISION');
  });
 }
}
test('argparse: direct format rejects malformed precision before invoking an argument callback', () => {
 for (const precision of [NaN, Infinity, -Infinity, -1, true, false, null, '', 'garbage', {}, [], '0']) {
  const tree = sprintf.parse('%.2g'); tree[0][7] = precision; let called = false;
  assert.throws(() => sprintf.format(tree, ['%.2g', () => { called = true; return 1; }]), e => e.code === 'ERR_SPRINTF_PRECISION');
  assert.equal(called, false);
 }
});
test('argparse: retained valid numeric, named, positional and string formats', () => {
 assert.equal(sprintf('%.2f %s', 1.25, 'done'), '1.25 done');
 assert.equal(sprintf('%(name)s', { name: 'sample' }), 'sample');
 assert.equal(sprintf('%2$s %1$d', 7, 'item'), 'item 7');
 assert.equal(sprintf('%.100f', 1).length, 102);
 assert.equal(sprintf('%.100e', 1), (1).toExponential(100));
 assert.equal(sprintf('%.100g', 1), (1).toPrecision(100));
 assert.equal(sprintf('%.101s', 'short'), 'short');
});
test('direct expansion bounds nested queue values as well as AST nodes', () => {
 const braces = require('braces'); let value = 'x';
 for (let i = 0; i < 8000; i++) value = [value];
 assert.throws(() => braces.expand({ type: 'root', nodes: [{ type: 'text', value }] }), e => e.code === 'ERR_BRACES_DEPTH');
});
test('format snapshots precision before caller-controlled getters or callbacks can mutate it', () => {
 const callbackTree = sprintf.parse('%.2f');
 assert.equal(sprintf.format(callbackTree, ['%.2f', () => { callbackTree[0][7] = '1000'; return 1; }]), '1.00');
 const getterTree = sprintf.parse('%.2f'); let reads = 0;
 Object.defineProperty(getterTree[0], 7, { get() { return ++reads === 1 ? '2' : '1000'; } });
 assert.equal(sprintf.format(getterTree, ['%.2f', 1]), '1.00'); assert.equal(reads, 1);
});

for (const entry of ['src/sprintf.js', 'dist/sprintf.min.js']) {
 test(`sprintf ${entry}: distributed formatter retains valid output and rejects excessive precision`, () => {
  const { sprintf: format, vsprintf: vectorFormat } = argparse(`sprintf-js/${entry}`);
  for (const conversion of ['e', 'f', 'g']) {
   const pattern = `%.101${conversion}`;
   for (const call of [() => format(pattern, 1), () => vectorFormat(pattern, [1]), () => format.format(format.parse(pattern), [pattern, 1])]) {
    assert.throws(call, e => e.code === 'ERR_SPRINTF_PRECISION');
   }
   const tree = format.parse(`%.2${conversion}`);
   const expected = format(`%.2${conversion}`, 1);
   assert.equal(format.format(tree, ['', () => { tree[0][7] = '1000'; tree[0][8] = 'g'; return 1; }]), expected);
  }
  assert.equal(format('%.2f %s', 1.25, 'done'), '1.25 done');
 });
}
