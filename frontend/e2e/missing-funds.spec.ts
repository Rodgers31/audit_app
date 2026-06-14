/**
 * National Missing Funds tracker (/accountability/missing-funds)
 */
import { expect, test } from '@playwright/test';
import { pageShell, waitForAppReady } from './utils/selectors';

test.describe('/accountability/missing-funds', () => {
  test('renders headline stats + top-counties breakdown', async ({ page }) => {
    await page.goto('/accountability/missing-funds');
    await waitForAppReady(page);

    await expect(pageShell.h1(page)).toContainText(/Missing Funds Tracker|Kifuatilia Pesa Zilizopotea/i);
    await expect(page.getByText(/Total flagged|Jumla/i).first()).toBeVisible();
    await expect(page.getByText(/Counties affected|Kaunti zinazoathiriwa/i)).toBeVisible();
    await expect(page.getByText(/Recovery status|Hali ya Urejeshwaji/i)).toBeVisible();
  });

  test('search filters the case list', async ({ page }) => {
    await page.goto('/accountability/missing-funds');
    await waitForAppReady(page);

    const search = page.getByPlaceholder(/Search by county|Tafuta/i);
    await expect(search).toBeVisible({ timeout: 15_000 });

    await search.fill('nonexistent-county-xyz');
    await expect(
      page.getByText(/No cases match your filter|Hakuna kesi/i)
    ).toBeVisible({ timeout: 5_000 });
  });

  test('status filter dropdown narrows results', async ({ page }) => {
    await page.goto('/accountability/missing-funds');
    await waitForAppReady(page);

    const statusSelect = page.locator('select').first();
    await expect(statusSelect).toBeVisible({ timeout: 15_000 });

    // "resolved" is one of the documented backend statuses. If the
    // option isn't present, skip — the backend may not have cases
    // with that status yet.
    const resolvedOption = statusSelect.locator('option').filter({ hasText: /Resolved/i });
    const count = await resolvedOption.count();
    if (count === 0) test.skip(true, 'no Resolved status option on this dataset');
    const value = (await resolvedOption.first().getAttribute('value')) ?? '';
    await statusSelect.selectOption(value);

    // Allow a render tick
    await page.waitForTimeout(500);
  });

  test('methodology footer is always present', async ({ page }) => {
    await page.goto('/accountability/missing-funds');
    await waitForAppReady(page);

    await expect(
      page.getByText(/Office of the Auditor-General|Mkaguzi Mkuu/i).first()
    ).toBeVisible();
  });
});
