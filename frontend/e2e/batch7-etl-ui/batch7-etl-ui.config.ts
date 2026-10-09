import { defineConfig, devices } from '@playwright/test';
export default defineConfig({
  testDir: '.', testMatch: 'batch7-etl-ui.spec.ts',
  outputDir: process.env.BATCH7_ETL_UI_ARTIFACTS || '../../test-results/batch7-etl-ui',
  workers: 1, retries: 0, timeout: 30000, reporter: 'list',
  use: {baseURL: 'http://127.0.0.1:3162', trace:'retain-on-failure'},
  projects:[{name:'chromium',use:{...devices['Desktop Chrome']}}],
});
