/**
 * County Explorer list (/counties)
 */
import { expect, test } from '@playwright/test';
import { pageShell, waitForAppReady } from './utils/selectors';

test.describe('/counties', () => {
  test('loads with header, subtitle, and populated list', async ({ page }) => {
    await page.goto('/counties');
    await waitForAppReady(page);

    await expect(pageShell.h1(page)).toContainText(/County Explorer|Kivinjari cha Kaunti/i);
    // Subtitle mentions 47 counties — stable across i18n variants
    await expect(page.locator('body')).toContainText(/47/);

    // At least Nairobi + Mombasa should render somewhere in the list
    await page.getByRole('button', { name: 'View All Counties', exact: true }).click();
    await expect(page.locator('table tbody tr')).toHaveCount(47);
    await expect(page.getByRole('link', { name: 'Nairobi', exact: true }).first()).toBeVisible();
    await expect(page.getByRole('link', { name: 'Mombasa', exact: true }).first()).toBeVisible();
  });

  test('search input filters the list', async ({ page }) => {
    await page.goto('/counties');
    await waitForAppReady(page);

    const search = page.getByRole('searchbox').first();
    await expect(search).toBeVisible({ timeout: 10_000 });

    await search.fill('Mombasa');
    // Nairobi should drop off, Mombasa should stay
    await expect(page.locator('table tbody tr')).toHaveCount(1);
    await expect(page.locator('table tbody tr')).toContainText('Mombasa');
    // Nairobi tile presence is contingent; assert its *exact tile* isn't visible
    // while still allowing "Nairobi" to appear inside unrelated header copy.
    const nairobiTile = page.getByRole('link', { name: /Nairobi/i }).first();
    await expect(nairobiTile).toHaveCount(0);
  });

  test('clicking a county tile navigates to its detail page', async ({ page }) => {
    await page.goto('/counties');
    await waitForAppReady(page);

    await page.getByRole('searchbox').first().fill('Nairobi');
    const nairobi = page
      .getByRole('link', { name: /Nairobi/i })
      .first();
    await nairobi.click();

    await page.waitForURL(/\/counties\/[\w-]+/, { timeout: 15_000 });
    await expect(page).toHaveURL(/\/counties\/[\w-]+/);
  });
});
