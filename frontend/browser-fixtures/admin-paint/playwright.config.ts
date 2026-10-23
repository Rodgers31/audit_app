import { defineConfig } from '@playwright/test';
const baseURL = process.env.ISSUE774_PAINT_URL;
if (!baseURL || !/^http:\/\/127\.0\.0\.1:3361[01]$/.test(baseURL)) {
  throw new Error('Explicit owned paint fixture URL required');
}
export default defineConfig({
  testDir: '.', testMatch: 'paint.spec.ts', workers: 1, retries: 0,
  use: { baseURL, channel: 'chrome', viewport: { width: 1365, height: 900 } },
});
