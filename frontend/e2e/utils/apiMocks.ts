import type { Page } from '@playwright/test';

/** Explicit bad responses for browser-only requests. SSR-backed pages must
 * change period first to execute these routes; tests count intercepted calls. */
export async function registerFailingApiMocks(page: Page): Promise<void> {
  await page.route('**/api/v1/**', route => route.fulfill({
    status: 500, json: { detail: 'synthetic-induced 500' },
  }));
}
