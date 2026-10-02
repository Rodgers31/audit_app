import { expect, test } from '@playwright/test';
import { countyResponse } from './utils/countyResponse';

for (const path of ['/counties', '/counties/001', '/sources', '/accountability/unaccounted-funds', '/debt', '/budget']) {
  test(`${path} — handles failed browser reads without certifying unavailable data`, async ({ page }) => {
    test.fixme(path === '/counties/001', 'Failed lazy Follow the Money reads render a blank panel without an unavailable state; #291 follow-up.');
    const errors: string[] = []; page.on('pageerror', err => errors.push(err.message));
    let calls = 0;
    if (path === '/counties') {
      await countyResponse(page, route => route.fulfill({ status: 500, json: { detail: 'Synthetic failed read' } }));
      await expect(page.getByText('Failed to load counties', { exact: true })).toBeVisible();
    } else {
      await page.route('**/api/v1/**', route => {
        calls++;
        return route.fulfill({ status: 500, json: { detail: 'Synthetic failed read' } });
      });
      await page.goto(path);
      if (path === '/counties/001') await page.getByRole('button', { name: 'Follow the Money', exact: true }).click();
      await expect.poll(() => calls).toBeGreaterThan(0);
      if (path === '/counties/001') {
        // Successful SSR overview remains valid; failed lazy panel must not
        // silently render a blank panel as a successful financial read.
        await expect(page.getByText('KES 10.00B', { exact: true })).toBeVisible();
        await expect(page.getByRole('heading', { name: /Follow the Money/i })).toBeVisible();
      } else if (path === '/budget') {
        // The successful SSR fiscal record stays visible; the failed freshness
        // read must remain unknown. Browser routing cannot replace SSR data.
        await expect(page.getByRole('heading', { name: 'KES 180B approved for FY 2025/26' })).toBeVisible();
        await expect(page.getByRole('status', { name: /^Data freshness:/ })).toContainText('Freshness unknown');
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
