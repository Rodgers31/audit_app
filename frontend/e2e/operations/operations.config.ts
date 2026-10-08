import { defineConfig, devices } from '@playwright/test';
export default defineConfig({
  testDir: '.', testMatch:'operations.spec.ts', outputDir:'operations-results',
  workers:1, retries:0, reporter:'list', timeout:30_000,
  use:{baseURL:'http://127.0.0.1:3152',trace:'retain-on-failure',screenshot:'only-on-failure'},
  projects:[{name:'chromium',use:{...devices['Desktop Chrome']}}],
});
