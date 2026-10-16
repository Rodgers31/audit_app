import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: '.',
  testMatch: 'loading.spec.ts',
  workers: 1,
  retries: 0,
  use: { baseURL: 'http://127.0.0.1:33508', channel: 'chrome', contextOptions: { reducedMotion: 'reduce' } },
});
