import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: '.', testMatch: 'batch7_coordinator_integration.spec.ts',
  outputDir: process.env.BATCH7_COORDINATOR_BROWSER_ARTIFACTS || '../../test-results/batch7-coordinator-integration',
  workers: 1, retries: 0, timeout: 45000, reporter: 'list',
  use: { baseURL: 'http://127.0.0.1:3163', trace: 'retain-on-failure' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
