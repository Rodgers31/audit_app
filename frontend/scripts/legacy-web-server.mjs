import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { legacyEnvironment } from './legacy-e2e-env.mjs';
for (const name of ['.env', '.env.local', '.env.production', '.env.production.local']) {
  if (existsSync(name)) throw new Error(`Synthetic browser build refuses ${name}; use a clean checkout`);
}
const env = legacyEnvironment();
console.log('RESOLVED production-Next.js API=127.0.0.1:8141 frontend=127.0.0.1:3141 synthetic=true env=allowlisted');
let child;
const run = args => new Promise(resolve => {
  child = spawn(process.execPath, ['node_modules/next/dist/bin/next', ...args], { env, stdio: 'inherit' });
  child.once('exit', code => resolve(code ?? 1));
});
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => child?.kill(signal));
const built = await run(['build']);
process.exitCode = built === 0 ? await run(['start', '--hostname', '127.0.0.1', '--port', '3141']) : built;
