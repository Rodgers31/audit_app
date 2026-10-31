'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { createRequire } = require('node:module');
const { test } = require('node:test');

const core = createRequire(require.resolve('@jest/core'));
const config = createRequire(core.resolve('jest-config'));
const packageRoot = path.dirname(config.resolve('deepmerge/package.json'));
const browser = {};
vm.runInNewContext(fs.readFileSync(path.join(packageRoot, 'dist/umd.js'), 'utf8'), browser);
const variants = [
  ['Jest resolved CommonJS', config('deepmerge')],
  ['UMD CommonJS', require(path.join(packageRoot, 'dist/umd.js'))],
  ['UMD browser', browser.deepmerge],
];

function ordinary(object, key = 'injected') {
  assert.equal(object[key], undefined, 'returned object inherited an attacker property');
  assert.equal(Object.hasOwn(object, '__proto__'), false);
  // Browser objects have a different realm's Object.prototype.
  assert.equal(Object.getPrototypeOf(Object.getPrototypeOf(object)), null);
  assert.equal(Object.hasOwn(Object.getPrototypeOf(object), key), false);
  assert.equal(({})[key], undefined);
}

for (const [name, merge] of variants) {
  test(`${name}: source cannot change a null-prototype target's returned prototype`, () => {
    const result = merge(Object.create(null), JSON.parse('{"__proto__":{"injected":true},"safe":1}'));
    ordinary(result);
    assert.equal(result.safe, 1);
  });

  test(`${name}: target copy rejects an own prototype key before reading its value`, () => {
    const target = JSON.parse('{"__proto__":{"injected":true},"safe":1}');
    ordinary(merge(target, {}));
    Object.defineProperty(target, '__proto__', { enumerable: true, get() { throw Error('forbidden getter'); } });
    assert.equal(merge(target, {}).safe, 1);
  });

  test(`${name}: source prototype getter is skipped even with an own target key`, () => {
    const target = JSON.parse('{"__proto__":{"injected":true}}');
    const source = Object.create(null);
    Object.defineProperty(source, '__proto__', { enumerable: true, get() { throw Error('forbidden getter'); } });
    ordinary(merge(target, source));
  });

  for (const placeholder of [null, undefined, false, 0, '', 'text']) {
    test(`${name}: nested ${String(placeholder)} placeholder cannot inherit source prototype data`, () => {
      const result = merge({ session: placeholder }, JSON.parse('{"session":{"__proto__":{"injected":true},"safe":2}}'));
      ordinary(result.session);
      assert.equal(result.session.safe, 2);
    });
  }

  test(`${name}: default array clones and merge.all cannot copy a prototype key`, () => {
    const source = JSON.parse('{"rows":[{"__proto__":{"injected":true},"safe":3}]}');
    ordinary(merge({}, source).rows[0]);
    ordinary(merge.all([Object.create(null), JSON.parse('{"__proto__":{"injected":true}}')]));
  });

  test(`${name}: forbidden keys never reach custom merge callbacks`, () => {
    const keys = [];
    const result = merge(JSON.parse('{"__proto__":{},"safe":{}}'),
      JSON.parse('{"__proto__":{"injected":true},"safe":{"value":4}}'),
      { customMerge(key) { keys.push(key); } });
    ordinary(result);
    assert.deepEqual(keys, ['safe']);
    assert.equal(result.safe.value, 4);
  });

  test(`${name}: objects, arrays, symbols, dates, and merge options retain their contracts`, () => {
    const symbol = Symbol('config');
    const date = new Date('2026-10-31T00:00:00Z');
    const target = { nested: { a: 1 }, rows: [1], date, [symbol]: { a: 2 } };
    const source = { nested: { b: 3 }, rows: [2], [symbol]: { b: 4 } };
    const result = merge(target, source);
    assert.equal(result.nested.a, 1); assert.equal(result.nested.b, 3);
    assert.deepEqual(Array.from(result.rows), [1, 2]);
    assert.equal(result[symbol].a, 2); assert.equal(result[symbol].b, 4);
    assert.equal(result.date, date);
    assert.notEqual(result.nested, target.nested);
    assert.deepEqual(target.nested, { a: 1 });
    assert.equal(merge({}, source, { clone: false }).nested, source.nested);
    const arrays = merge({ rows: [1] }, { rows: [2] }, { arrayMerge: (_a, b) => b });
    assert.deepEqual(arrays.rows, [2]);
    assert.equal(merge({ value: {} }, { value: {} }, { customMerge: key => key === 'value' ? () => 7 : undefined }).value, 7);
    const data = merge({ constructor: { a: 1 }, prototype: { a: 1 } }, { constructor: { b: 2 }, prototype: { b: 2 } });
    assert.equal(data.constructor.a, 1); assert.equal(data.constructor.b, 2);
    assert.equal(data.prototype.a, 1); assert.equal(data.prototype.b, 2);
    assert.equal(data.constructor.prototype, undefined);
    assert.throws(() => merge.all({}), /array/);
  });
}
