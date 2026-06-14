/**
 * Error-state coverage.
 *
 * Intentionally mocks every `/api/v1/*` endpoint to 500 and asserts
 * that each page degrades gracefully — the user sees some kind of
 * error message instead of a blank white screen or a thrown React
 * error boundary.
 */
import { expect, test } from '@playwright/test';
import { registerFailingApiMocks } from './utils/apiMocks';

const PAGES_WITH_DATA = [
  '/counties',
  '/counties/001',
  '/sectors',
  '/sources',
  '/accountability/missing-funds',
  '/debt',
  '/budget',
];

test.describe('API failures', () => {
  test.beforeEach(async ({ page }) => {
    await registerFailingApiMocks(page);
  });

  for (const path of PAGES_WITH_DATA) {
    test(`${path} — does not crash when every endpoint returns 500`, async ({ page }) => {
      const errors: string[] = [];
      page.on('pageerror', (err) => errors.push(err.message));

      await page.goto(path);

      // Page renders *something* — header + footer must still be there.
      await expect(page.getByRole('banner')).toBeVisible({ timeout: 15_000 });
      await expect(page.getByRole('contentinfo')).toBeVisible();

      // An error banner, "failed to load" copy, or a retry button is
      // acceptable — anything but a React crash.
      await expect(page.locator('body')).toContainText(
        /Failed to load|unavailable|error|Something went wrong|try again|retry/i,
        { timeout: 15_000 }
      );

      // No uncaught React errors should bubble
      expect(errors).toEqual([]);
    });
  }
});

test.describe('Slow network', () => {
  test('/counties shows a loading state before data arrives', async ({ page }) => {
    // Delay every API response by 3 s — long enough to see the loader.
    await page.route('**/api/v1/**', async (route) => {
      await new Promise((r) => setTimeout(r, 3000));
      return route.continue();
    });

    await page.goto('/counties');

    // At least one of the common loading indicators should appear first.
    await expect(
      page.locator('[class*="animate-spin"], [class*="Skeleton"], [class*="skeleton"]').first()
    ).toBeVisible({ timeout: 5_000 });
  });
});
