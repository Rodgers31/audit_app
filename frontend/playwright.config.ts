import { defineConfig, devices } from '@playwright/test';
import { legacyEnvironment } from './scripts/legacy-e2e-env.mjs';

// Original suite only. The publication acceptance config retains its separate
// real API/refresh controls and ports. Both jobs use a production Next.js build.
export default defineConfig({
  testDir: 'e2e',
  testIgnore: '**/acceptance/**',
  outputDir: 'legacy-results',
  timeout: 30_000,
  expect: { timeout: 10_000 },
  workers: 2,
  retries: 0,
  forbidOnly: !!process.env.CI,
  reporter: [['list'], ['html', { outputFolder: 'legacy-report', open: 'never' }],
    ['json', { outputFile: 'legacy-results/results.json' }]],
  use: {
    baseURL: 'http://127.0.0.1:3141',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit', use: { ...devices['Desktop Safari'] } },
  ],
  webServer: [
    {
      command: `${process.env.BROWSER_TEST_PYTHON || 'python'} ../backend/tests/legacy_browser_fixture_api.py`,
      url: 'http://127.0.0.1:8141/health',
      reuseExistingServer: false,
      timeout: 60_000,
      env: legacyEnvironment(),
    },
    {
      command: 'node scripts/legacy-web-server.mjs',
      url: 'http://127.0.0.1:3141',
      reuseExistingServer: false,
      timeout: 240_000,
      env: legacyEnvironment(),
    },
  ],
});
