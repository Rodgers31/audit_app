import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { SourceTextModule, SyntheticModule } from 'node:vm';
import * as path from 'node:path';

test('the executed fixture launcher binds its child server only to loopback', async () => {
  let childArgs;
  const source = await readFile(new URL('./serve.mjs', import.meta.url), 'utf8');
  const module = new SourceTextModule(source);
  await module.link(async name => {
    const exports = name === 'node:fs/promises' ? {
      mkdir: async () => {}, writeFile: async () => {}, symlink: async () => {},
      readFile: async (_path, encoding) => encoding ? '' : Buffer.alloc(0),
    } : name === 'node:path' ? { resolve: path.resolve } : {
      spawn: (_command, args) => { childArgs = args; return { kill() {} }; },
    };
    return new SyntheticModule(Object.keys(exports), function () { for (const [key, value] of Object.entries(exports)) this.setExport(key, value); });
  });
  await module.evaluate();
  assert.equal(childArgs[childArgs.indexOf('--hostname') + 1], '127.0.0.1');
});
