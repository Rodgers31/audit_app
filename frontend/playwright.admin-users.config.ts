import { defineConfig, devices } from '@playwright/test';
export default defineConfig({
  testDir: 'e2e/admin-users',
  outputDir: 'admin-users-results',
  workers: 1,
  retries: 0,
  timeout: 45000,
  reporter: [['list']],
  use: { baseURL: 'http://127.0.0.1:3151', trace: 'retain-on-failure' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
