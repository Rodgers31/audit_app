import { defineConfig, devices } from '@playwright/test';
import { resolve } from 'path';
const frontend = resolve(__dirname, '../..');
export default defineConfig({
  testDir: '.', testMatch: '*.spec.ts', outputDir: '/tmp/batch6-admin-overview-audit-results',
  workers: 1, retries: 0, timeout: 45_000, reporter: 'list',
  use: { baseURL: 'http://127.0.0.1:3153', trace: 'retain-on-failure', ...devices['Desktop Chrome'] },
  webServer: [
    { command: `${process.env.BROWSER_TEST_PYTHON || 'python3'} ../backend/tests/admin_overview_audit/browser_api.py`, cwd: frontend, url: 'http://127.0.0.1:8153/health', reuseExistingServer: false, env: { PYTHON_DOTENV_DISABLED: '1' }, timeout: 60_000 },
    { command: 'node node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port 3153', cwd: frontend, url: 'http://127.0.0.1:3153', reuseExistingServer: false, timeout: 120_000,
      env: { NEXT_PUBLIC_API_URL: 'http://127.0.0.1:8153', NEXT_PUBLIC_SUPABASE_URL: 'http://127.0.0.1:8153', NEXT_PUBLIC_SUPABASE_ANON_KEY: 'inert-overview-anon', NEXT_TELEMETRY_DISABLED: '1' } },
  ],
});
