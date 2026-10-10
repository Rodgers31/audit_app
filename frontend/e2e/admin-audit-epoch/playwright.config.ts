import { defineConfig, devices } from '@playwright/test';
import { execFileSync } from 'child_process';
import { randomBytes } from 'crypto';
import { existsSync, lstatSync, mkdirSync, readFileSync, realpathSync, statSync, writeFileSync } from 'fs';
import { dirname, isAbsolute, join, resolve, sep } from 'path';

const frontend = resolve(__dirname, '../..');
const root = dirname(frontend);
const output = process.env.ISSUE611_BROWSER_OUTPUT;
const python = process.env.ISSUE611_BROWSER_PYTHON;
const pgPort = process.env.ISSUE611_PG_PORT || '55534';
if (!['55534', '55545'].includes(pgPort)) throw new Error('Explicit owned PostgreSQL port required');
const apiPort = pgPort === '55545' ? 18045 : 18034;
const uiPort = pgPort === '55545' ? 13045 : 13034;
const apiURL = `http://127.0.0.1:${apiPort}`;
if (!output || !python || !isAbsolute(output) || !isAbsolute(python) || !statSync(python).isFile()) {
  throw new Error('Explicit absolute owned runtime and fresh output required');
}
const git = (...args: string[]) => execFileSync('git', args, { cwd: root, encoding: 'utf8' }).trim();
const excluded = [git('rev-parse', '--path-format=absolute', '--git-common-dir'),
  ...git('worktree', 'list', '--porcelain', '-z').split('\0').filter(row => row.startsWith('worktree ')).map(row => row.slice(9))];
// lstat also rejects a dangling destination symlink before any reporter writes.
let occupied = existsSync(output);
try { lstatSync(output); occupied = true; } catch (error) {
  if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error;
}
if (resolve(output) !== output || realpathSync(dirname(output)) !== dirname(output) ||
  output.split(sep).includes('.git') || excluded.some(path => output === path || output.startsWith(path + sep))) {
  throw new Error('External unsymlinked browser output required; Git metadata and all checkouts excluded');
}
const marker = join(output, '.issue611-run');
// Playwright loads this config again in its workers. The coordinator reserves
// a fresh directory once; workers must prove they inherited that same run.
if (!process.env.TEST_WORKER_INDEX) {
  if (occupied) throw new Error('Fresh browser output required');
  mkdirSync(output, { mode: 0o700 });
  const nonce = randomBytes(32).toString('hex');
  writeFileSync(marker, nonce, { flag: 'wx', mode: 0o600 });
  const identity = lstatSync(output);
  process.env.ISSUE611_BROWSER_CAPTURE = JSON.stringify({ output, nonce, dev: identity.dev, ino: identity.ino });
} else {
  const capture = JSON.parse(process.env.ISSUE611_BROWSER_CAPTURE || 'null');
  const identity = lstatSync(output);
  if (!capture || !/^[0-9]+$/.test(process.env.TEST_WORKER_INDEX) || !identity.isDirectory() ||
    identity.isSymbolicLink() || realpathSync(output) !== output || lstatSync(marker).isSymbolicLink() ||
    capture.output !== output || capture.dev !== identity.dev || capture.ino !== identity.ino ||
    !/^[0-9a-f]{64}$/.test(capture.nonce) || readFileSync(marker, 'utf8') !== capture.nonce) {
    throw new Error('Owned browser worker output identity required');
  }
}
const shellQuote = (value: string) => "'" + value.replaceAll("'", "'\\''") + "'";
export default defineConfig({
  testDir: '.', workers: 1, retries: 0, timeout: 45_000,
  reporter: [['list'], ['json', { outputFile: join(output, 'report.json') }]],
  outputDir: join(output, 'test-results'),
  use: { baseURL: `http://127.0.0.1:${uiPort}`, trace: 'retain-on-failure', ...devices['Desktop Chrome'] },
  webServer: [
    { command: `${shellQuote(python)} ../docs/admin/implementation/batch11-issue-611-evidence/browser_api.py`, cwd: frontend, url: apiURL + '/health', reuseExistingServer: false, timeout: 60_000,
      env: { PYTHON_DOTENV_DISABLED: '1', ISSUE611_OWNED_POSTGRES: '1', ISSUE611_PG_PORT: pgPort, SUPABASE_JWT_SECRET: 'issue611-inert-key', DATABASE_URL: `postgresql+psycopg2://inert:inert@127.0.0.1:${pgPort}/issue611`, SUPABASE_URL: apiURL, SUPABASE_SERVICE_ROLE_KEY: 'inert', AUTO_SEEDER_ENABLED: 'false', AUTO_WARMUP_ENABLED: 'false', ENABLE_ETL_SCHEDULER: 'false' } },
    { command: `node node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port ${uiPort}`, cwd: frontend, url: `http://127.0.0.1:${uiPort}`, reuseExistingServer: false, timeout: 120_000,
      env: { NEXT_PUBLIC_API_URL: apiURL, NEXT_PUBLIC_SUPABASE_URL: apiURL, NEXT_PUBLIC_SUPABASE_ANON_KEY: 'inert', NEXT_TELEMETRY_DISABLED: '1' } },
  ],
});
