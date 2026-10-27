"use strict";

// Package engines select compatibility; this checks the binary actually running.
function isSupportedNode(version) {
  if (typeof version !== 'string' || version.length > 64) return false;
  const parts = /^24\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/.exec(version);
  if (!parts) return false;
  const minor = Number(parts[1]), patch = Number(parts[2]);
  return Number.isSafeInteger(minor) && Number.isSafeInteger(patch) &&
    (minor > 22 || (minor === 22 && patch >= 1));
}

if (require.main === module) {
  if (!isSupportedNode(process.versions.node)) {
    console.error('Unsupported Node runtime. Use Node 24.22.1 or a later stable 24.x patch.');
    process.exitCode = 1;
  } else {
    console.log(JSON.stringify({ check: 'node-runtime', node: process.version, supported: true }));
  }
}

module.exports = { isSupportedNode };
