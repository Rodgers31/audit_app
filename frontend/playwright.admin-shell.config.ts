import { defineConfig, devices } from '@playwright/test';
import { existsSync } from 'node:fs';
import { resolve } from 'node:path';

for (const name of ['.env', '.env.local', '.env.production', '.env.production.local']) {
  if (existsSync(resolve(__dirname, name))) throw new Error(`Admin shell fixture refuses ${name}; use a clean checkout`);
}

// This suite builds the actual app, including RootLayout, middleware, providers,
// Navigation, /admin layout, /status and the unmodified production CSS pipeline.
// Run locally with npm run test:admin-shell; no hosted workflow is enabled here.
export default defineConfig({
  testDir: './browser-fixtures/admin-shell',
  testMatch: '*.spec.ts',
  outputDir: './test-results/admin-shell',
  workers: 1,
  retries: 0,
  timeout: 45_000,
  expect: { timeout: 12_000 },
  reporter: [['list']],
  use: { baseURL: 'http://127.0.0.1:3137', ...devices['Desktop Chrome'], screenshot: 'only-on-failure', trace: 'retain-on-failure' },
  webServer: [
    { command: 'node browser-fixtures/admin-shell/service.cjs', url: 'http://127.0.0.1:8137/health', reuseExistingServer: false },
    {
      command: 'npm run build && npm start -- --hostname 127.0.0.1 --port 3137',
      url: 'http://127.0.0.1:3137', timeout: 240_000, reuseExistingServer: false,
      env: { CIRCLE_NODE_TOTAL: '3', NEXT_TELEMETRY_DISABLED: '1', INTERNAL_API_URL: 'http://127.0.0.1:8137', NEXT_PUBLIC_API_URL: 'http://127.0.0.1:8137', NEXT_PUBLIC_SUPABASE_URL: 'http://127.0.0.1:8137', NEXT_PUBLIC_SUPABASE_ANON_KEY: 'inert-shell-anon-key' },
    },
  ],
});
