import { defineConfig, devices } from '@playwright/test';

// This bounded suite is a PR gate. The historical multi-browser suite remains
// separately runnable; see docs/operations/2026-09-27-freshness-browser.md.
export default defineConfig({
  testDir: './e2e/acceptance',
  outputDir: './acceptance-results',
  timeout: 45_000,
  expect: { timeout: 12_000 },
  workers: 1,
  retries: 0,
  reporter: [['list'], ['html', { outputFolder: 'acceptance-report', open: 'never' }]],
  use: {
    baseURL: 'http://127.0.0.1:3125',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    ...devices['Desktop Chrome'],
  },
  webServer: [
    {
      command: `${process.env.BROWSER_TEST_PYTHON || 'python'} ../backend/tests/browser_fixture_api.py`,
      url: 'http://127.0.0.1:8125/health',
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: 'npm run build && npm start -- --hostname 127.0.0.1 --port 3125',
      url: 'http://127.0.0.1:3125',
      reuseExistingServer: false,
      timeout: 240_000,
      env: {
        NEXT_PUBLIC_API_URL: 'http://127.0.0.1:8125',
        NEXT_PUBLIC_SUPABASE_URL: 'http://127.0.0.1:8125',
        NEXT_PUBLIC_SUPABASE_ANON_KEY: 'browser-test-only-anon-key',
        REVALIDATE_SECRET: 'browser-test-only-secret',
      },
    },
  ],
});
