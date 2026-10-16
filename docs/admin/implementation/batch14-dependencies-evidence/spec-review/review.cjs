'use strict';
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const child = spawnSync('python3', ['-I', path.join(__dirname, '../portable-replay.py'), 'spec', ...process.argv.slice(2)], {stdio:'inherit'});
if (child.error) { console.error(child.error.message); process.exitCode = 1; }
else process.exitCode = child.status === null ? 1 : child.status;
