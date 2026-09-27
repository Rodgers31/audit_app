import { expect, test } from '@playwright/test';

const fresh = (source: string, status = 'fresh') => ({
  source, label: source, status, last_updated: new Date().toISOString().slice(0, 10),
  covers_through: 'FY2025/26 9M', update_frequency: 'Quarterly',
});

for (const [name, sources, label] of [
  ['partial', [fresh('COB')], 'Freshness unknown'],
  ['complete', [fresh('COB'), fresh('Treasury')], 'Up to date'],
  ['stale', [fresh('COB'), fresh('Treasury', 'stale')], 'May be stale'],
  ['unavailable', [], 'Freshness unknown'],
] as const) {
  test(`budget freshness is ${name}`, async ({ page }) => {
    await page.route('**/api/v1/data/freshness', route => route.fulfill({ json: { sources } }));
    await page.goto('/budget');
    const badge = page.getByRole('status', { name: /^Data freshness:/ });
    await expect(badge).toContainText(label);
    if (name !== 'complete') await expect(badge).not.toContainText('Up to date');
  });
}

test('no JavaScript readers receive an honest resolved absence', async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  await page.goto('http://127.0.0.1:3125/budget');
  await expect(page.getByRole('status', { name: /^Data freshness:/ })).toContainText('Freshness unknown');
  await expect(page.getByText('Checking data freshness…', { exact: true })).toHaveCount(0);
  await context.close();
});
