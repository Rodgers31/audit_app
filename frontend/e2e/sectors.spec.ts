/**
 * National Sector Spending roll-up (/sectors)
 */
import { expect, test } from '@playwright/test';
import { pageShell, waitForAppReady } from './utils/selectors';

test.describe('/sectors', () => {
  test('renders the 3 top-line stats', async ({ page }) => {
    await page.goto('/sectors');
    await waitForAppReady(page);

    await expect(pageShell.h1(page)).toContainText(
      /Where counties actually spend|Pesa za kaunti/i
    );

    // The three hero stats — labels are i18n-keyed but the underlying text is stable.
    await expect(page.getByText(/Total allocated|Iliyotengwa jumla|Total planned/i)).toBeVisible();
    await expect(page.getByText(/Total executed|Iliyotumika jumla|Total spent/i)).toBeVisible();
    await expect(page.getByText(/execution rate|kiwango cha matumizi/i)).toBeVisible();
  });

  test('shows at least one sector card with an execution pill', async ({ page }) => {
    await page.goto('/sectors');
    await waitForAppReady(page);

    // "Health" is the top sector on real data — always present
    const healthArticle = page
      .locator('article')
      .filter({ hasText: /^Health/i })
      .first();
    await expect(healthArticle).toBeVisible({ timeout: 15_000 });
    await expect(healthArticle).toContainText(/executed|imetumika|spent/i);
  });

  test('clicking a sector card expands its top-counties drill-down', async ({ page }) => {
    await page.goto('/sectors');
    await waitForAppReady(page);

    const health = page.locator('article').filter({ hasText: /^Health/i }).first();
    await health.getByRole('button').first().click();

    // Drill-down shows top counties header
    await expect(
      page.getByText(/Top counties by/i).first()
    ).toBeVisible({ timeout: 5_000 });
  });
});
