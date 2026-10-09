'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

/**
 * Copy a read-only runtime tree into a new owned fixture without source links.
 * @param {string} original Existing directory or regular file; never written.
 * @param {string} destination Empty destination below the caller's owned root.
 * @param {Set<string>} ancestors Real directories already on this branch.
 * @returns {void} Reject cycles, special files and occupied destinations.
 */
function copyRuntimeFixture(original, destination, ancestors = new Set()) {
  assert.equal(fs.lstatSync(destination, { throwIfNoEntry: false }), undefined, 'Runtime fixture destination must be empty');
  const real = fs.realpathSync(original);
  const info = fs.statSync(real);
  if (info.isDirectory()) {
    assert.ok(!ancestors.has(real), 'Runtime fixture contains a directory link cycle');
    const branch = new Set(ancestors).add(real);
    fs.mkdirSync(destination);
    for (const name of fs.readdirSync(real)) copyRuntimeFixture(path.join(real, name), path.join(destination, name), branch);
  } else {
    assert.ok(info.isFile(), 'Runtime fixture contains an unsupported special file');
    fs.copyFileSync(real, destination);
    fs.chmodSync(destination, info.mode & 0o777);
  }
}

module.exports = { copyRuntimeFixture };
