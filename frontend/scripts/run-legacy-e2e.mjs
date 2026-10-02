import { spawn } from 'node:child_process';
import { legacyEnvironment } from './legacy-e2e-env.mjs';
const args = ['node_modules/@playwright/test/cli.js', 'test', '--config', 'playwright.config.ts',
  '--project=chromium', ...process.argv.slice(2)];
const child = spawn(process.execPath, args, { env: legacyEnvironment(), stdio: 'inherit' });
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => child.kill(signal));
child.once('exit', code => { process.exitCode = code ?? 1; });
