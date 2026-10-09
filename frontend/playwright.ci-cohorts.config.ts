import { defineConfig, devices } from '@playwright/test';
import { resolve } from 'node:path';
import { cohorts, cohortEnvironment, selectedCohort } from './scripts/ci-browser-cohorts.mjs';

const cohort = selectedCohort(process.env.BROWSER_TEST_COHORT);
const env = cohortEnvironment(cohort);
const shellQuote = (value: string) => `'${value.replaceAll("'", "'\"'\"'")}'`;

export default defineConfig({
  testDir: cohort.directory,
  testMatch: '**/*.spec.ts',
  testIgnore: cohort.name === 'public'
    ? ['**/acceptance/**', ...cohorts.filter(item => item.name !== 'public').map(item => `**/${item.directory.slice(4)}/**`)]
    : [],
  outputDir: resolve(`legacy-results/${cohort.name}`),
  timeout: cohort.timeout,
  expect: { timeout: 10000 },
  workers: cohort.workers,
  retries: 0,
  forbidOnly: !!process.env.CI,
  reporter: [['list'], ['html', { outputFolder: resolve(`legacy-report/${cohort.name}`), open: 'never' }],
    ['json', { outputFile: resolve(`legacy-results/${cohort.name}/results.json`) }]],
  use: {
    baseURL: `http://127.0.0.1:${cohort.web}`,
    trace: 'retain-on-failure', screenshot: 'only-on-failure', video: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    { command: `${shellQuote(process.env.BROWSER_TEST_PYTHON || 'python')} ${shellQuote(`../backend/tests/${cohort.fixture}`)}`,
      url: `http://127.0.0.1:${cohort.api}${cohort.health}`, reuseExistingServer: false, timeout: 60000, env },
    { command: 'node scripts/ci-cohort-web-server.mjs', url: `http://127.0.0.1:${cohort.web}`,
      reuseExistingServer: false, timeout: 240000, env },
  ],
});
