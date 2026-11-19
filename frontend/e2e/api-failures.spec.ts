import { expect, test } from '@playwright/test';
import { countyResponse } from './utils/countyResponse';

for (const path of ['/counties', '/counties/001', '/sources', '/accountability/unaccounted-funds', '/debt', '/budget']) {
  test(`${path} — handles failed browser reads without certifying unavailable data`, async ({ page }) => {
    const errors: string[] = []; page.on('pageerror', err => errors.push(err.message));
    let calls = 0;
    if (path === '/counties') {
      await countyResponse(page, route => route.fulfill({ status: 500, json: { detail: 'Synthetic failed read' } }));
      await expect(page.getByText('Failed to load counties', { exact: true })).toBeVisible();
    } else if (path === '/counties/001') {
      // Fail only the consumed lazy endpoint; county/year prerequisites succeed.
      const endpoint = '/api/v1/counties/001/money-flow';
      let failed = true;
      await page.route(url => url.pathname === endpoint, route => {
        calls++;
        return failed
          ? route.fulfill({ status: 500, json: { detail: 'Synthetic failed money-flow read' } })
          : route.continue();
      });
      await page.goto(path);
      await page.getByRole('tab', { name: 'Money', exact: true }).click();
      await expect.poll(() => calls).toBe(1);
      const unavailable = page.locator('[class*="moneyReport"]').getByRole('alert');
      await expect(unavailable).toContainText('Could not load money flow for this period.');
      await expect(page.getByText('No money flow data available for this period.')).toHaveCount(0);
      await expect(page.getByText('KES 10.00B', { exact: true })).toBeVisible();
      await expect(page.getByRole('combobox', { name: 'Fiscal year', exact: true })).toHaveValue('FY2025/26 9M');
      failed = false;
      await unavailable.getByRole('button', { name: 'Try again' }).click();
      await expect(page.getByRole('button', { name: /^Allocated KES/ })).toContainText('KES 10.00B');
      await expect(page.getByText(/Reported procurement commitments KES/).first()).toBeVisible();
      await expect(unavailable).toHaveCount(0);
      expect(calls).toBe(2);
    } else {
      const budgetFreshness = path === '/budget' ? page.waitForResponse('**/api/v1/data/freshness') : undefined;
      await page.route('**/api/v1/**', route => {
        calls++;
        return route.fulfill({ status: 500, json: { detail: 'Synthetic failed read' } });
      });
      await page.goto(path);
      await expect.poll(() => calls).toBeGreaterThan(0);
      if (path === '/budget') {
        // Browser routing cannot replace the successful SSR fiscal record. A
        // failed freshness read must leave the verdict absent.
        await expect(page.getByRole('heading', { name: 'KES 180B approved for FY 2025/26' })).toBeVisible();
        expect((await budgetFreshness)?.status()).toBe(500);
        await expect(page.getByText(/^(?:Up to date|May be stale|Out of date|Freshness unknown)(?: ·|$)/)).toHaveCount(0);
      } else {
        await expect(page.locator('body')).toContainText(/Failed to load|unavailable|could not|error|Something went wrong|try again|retry|No data/i);
      }
    }
    await expect(page.getByRole('banner')).toBeVisible();
    await expect(page.getByRole('contentinfo')).toBeVisible();
    expect(errors).toEqual([]);
  });
}

test('/counties shows a loading state before a new period arrives', async ({ page }) => {
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  await countyResponse(page, async route => { await pending; await route.fulfill({ response: await route.fetch() }); });
  await expect(page.locator('[class*="animate-spin"]').first()).toBeVisible();
  release();
  await expect(page.locator('table tbody tr').first()).toContainText('8.0B');
});
