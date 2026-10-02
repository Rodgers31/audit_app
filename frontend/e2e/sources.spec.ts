/**
 * Data Sources page (/sources)
 */
import { expect, test } from '@playwright/test';
import { pageShell, waitForAppReady } from './utils/selectors';

test.describe('/sources', () => {
  test('shows documents-indexed total + publishing-agencies count', async ({ page }) => {
    await page.goto('/sources');
    await waitForAppReady(page);

    await expect(pageShell.h1(page)).toContainText(
      /Where the data comes from|Vyanzo vya Data/i
    );
    await expect(page.getByText(/Documents indexed|Nyaraka zilizopangwa/i)).toBeVisible();
    await expect(page.getByText(/Publishing agencies|Mashirika/i)).toBeVisible();
  });

  test('lists the synthetic publishing agency card', async ({ page }) => {
    await page.goto('/sources');
    await waitForAppReady(page);

    const cob = page.getByRole('article').filter({ hasText: /Synthetic local fixture/ }).first();
    await expect(cob).toBeVisible({ timeout: 15_000 });
    await expect(cob).toContainText('2');
  });

  test('an agency without a website does not invent an external Visit-site link', async ({ page }) => {
    await page.goto('/sources');
    await expect(page.getByRole('article').filter({ hasText: 'Synthetic local fixture' })).toBeVisible();
    await expect(page.getByRole('link', { name: /Visit site/i })).toHaveCount(0);
  });
});
