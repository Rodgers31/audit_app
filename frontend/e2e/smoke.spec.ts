import { expect, test } from '@playwright/test';
import { registerApiMocks } from './utils/mockApi';

const criticalRoutes = [
  { path: '/', title: /Kenya/i },
  { path: '/budget', title: /Budget/i },
  { path: '/counties', title: /Counties|County/i },
  { path: '/debt', title: /Debt|Liabilities/i },
  { path: '/audits', title: /Audit/i },
];

test.describe('Frontend smoke', () => {
  test.beforeEach(async ({ page }) => {
    await registerApiMocks(page);
  });

  for (const route of criticalRoutes) {
    test(`should render ${route.path}`, async ({ page }) => {
      await page.goto(route.path);
      await expect(page).toHaveTitle(route.title);

      // Wait for main content to be visible (with longer timeout for data loading)
      await expect(page.locator('main')).toBeVisible({ timeout: 15000 });
    });
  }
});
