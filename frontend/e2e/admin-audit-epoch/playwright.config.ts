import { defineConfig, devices } from '@playwright/test';
import { execFileSync } from 'child_process';
import { realpathSync, statSync } from 'fs';
import { dirname, isAbsolute, join, resolve, sep } from 'path';

const frontend = resolve(__dirname, '../..');
const root = dirname(frontend);
const output = process.env.ISSUE611_BROWSER_OUTPUT;
const python = process.env.ISSUE611_BROWSER_PYTHON;
if (!output || !python || !isAbsolute(output) || !isAbsolute(python) || !statSync(python).isFile()) {
  throw new Error('Explicit absolute owned runtime and fresh output required');
}
const git = (...args: string[]) => execFileSync('git', args, { cwd: root, encoding: 'utf8' }).trim();
const excluded = [git('rev-parse', '--path-format=absolute', '--git-common-dir'),
  ...git('worktree', 'list', '--porcelain', '-z').split('\0').filter(row => row.startsWith('worktree ')).map(row => row.slice(9))];
if (resolve(output) !== output || realpathSync(dirname(output)) !== dirname(output) ||
  output.split(sep).includes('.git') || excluded.some(path => output === path || output.startsWith(path + sep))) {
  throw new Error('External unsymlinked browser output required; Git metadata and all checkouts excluded');
}
const shellQuote = (value: string) => "'" + value.replaceAll("'", "'\\''") + "'";
export default defineConfig({
  testDir: '.', workers: 1, retries: 0, timeout: 45_000,
  reporter: [['list'], ['json', { outputFile: join(output, 'report.json') }]],
  outputDir: join(output, 'test-results'),
  use: { baseURL: 'http://127.0.0.1:13034', trace: 'retain-on-failure', ...devices['Desktop Chrome'] },
  webServer: [
    { command: `${shellQuote(python)} ../docs/admin/implementation/batch11-issue-611-evidence/browser_api.py`, cwd: frontend, url: 'http://127.0.0.1:18034/health', reuseExistingServer: false, timeout: 60_000,
      env: { PYTHON_DOTENV_DISABLED: '1', ISSUE611_OWNED_POSTGRES: '1', SUPABASE_JWT_SECRET: 'issue611-inert-key', DATABASE_URL: 'postgresql+psycopg2://inert:inert@127.0.0.1:55534/issue611', SUPABASE_URL: 'http://127.0.0.1:18034', SUPABASE_SERVICE_ROLE_KEY: 'inert' } },
    { command: 'node node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port 13034', cwd: frontend, url: 'http://127.0.0.1:13034', reuseExistingServer: false, timeout: 120_000,
      env: { NEXT_PUBLIC_API_URL: 'http://127.0.0.1:18034', NEXT_PUBLIC_SUPABASE_URL: 'http://127.0.0.1:18034', NEXT_PUBLIC_SUPABASE_ANON_KEY: 'inert', NEXT_TELEMETRY_DISABLED: '1' } },
  ],
});
