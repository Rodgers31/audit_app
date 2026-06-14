/**
 * Side-by-side county comparison (/counties/compare?ids=...)
 */
import { expect, test } from '@playwright/test';
import { pageShell, waitForAppReady } from './utils/selectors';

test.describe('/counties/compare', () => {
  test('empty state prompts user to pick ≥2 counties', async ({ page }) => {
    await page.goto('/counties/compare');
    await waitForAppReady(page);

    await expect(pageShell.h1(page)).toContainText(/Compare counties|Linganisha Kaunti/i);
    await expect(
      page.getByText(/Pick at least two counties|Chagua angalau kaunti mbili/i)
    ).toBeVisible({ timeout: 15_000 });
  });

  test('deep link with ?ids=… pre-populates the table', async ({ page }) => {
    await page.goto('/counties/compare?ids=047,001,032');
    await waitForAppReady(page);

    // Table column headers should include each county
    await expect(page.getByRole('columnheader', { name: /Mombasa/i }).first()).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole('columnheader', { name: /Nairobi/i }).first()).toBeVisible();
    await expect(page.getByRole('columnheader', { name: /Nakuru/i }).first()).toBeVisible();

    // Section headers
    for (const s of ['Population & budget', 'Execution', 'Financial health']) {
      await expect(page.getByText(s, { exact: false }).first()).toBeVisible();
    }
  });

  test('county names in the table link to detail pages', async ({ page }) => {
    await page.goto('/counties/compare?ids=047,001');
    await waitForAppReady(page);

    const mombasaLink = page.getByRole('link', { name: /^Mombasa$/ }).first();
    await expect(mombasaLink).toBeVisible({ timeout: 15_000 });
    const href = await mombasaLink.getAttribute('href');
    expect(href).toMatch(/\/counties\/[\w-]+/);
  });
});
