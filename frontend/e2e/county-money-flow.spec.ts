import { expect, test } from '@playwright/test';
import fixture from './fixtures/county_money_flow.json';

test.use({ hasTouch: true, viewport: { width: 360, height: 820 }, reducedMotion: 'reduce' });

test('reads allocation/spent/unspent by touch and keyboard, exposes exact values and preserves the Audit destination', async ({ page }) => {
  await page.route('**/api/v1/counties/001/money-flow?*', route => route.fulfill({ json: fixture }));
  await page.goto('/counties/001?tab=money&fy=FY2024%2F25&from=money&keep=one&keep=two#record');
  const panel = page.getByRole('tabpanel', { name: 'Money', exact: true });
  const allocation = panel.getByRole('button', { name: 'Allocated KES 10.08B', exact: true });
  const spending = panel.getByRole('button', { name: /^Spent KES/ });
  const readout = panel.locator('[aria-live=polite]');
  await expect(panel.getByText('Nairobi County spent 76% of its allocation in FY2025/26 9M.')).toBeVisible();
  await allocation.tap();
  await expect(readout).toHaveText('Allocated · KES 10,080,000,000');
  await allocation.tap();
  await expect(readout).toBeEmpty();
  await spending.tap({ position: { x: (await spending.boundingBox())!.width * 0.9, y: 32 } });
  await expect(readout).toHaveText('Unspent · KES 2,410,000,000');
  await spending.tap({ position: { x: (await spending.boundingBox())!.width * 0.9, y: 32 } });
  await expect(readout).toBeEmpty();
  await spending.focus();
  await page.keyboard.press('Home');
  await expect(readout).toHaveText('Spent · KES 7,670,000,000');
  await page.keyboard.press('End');
  await expect(readout).toHaveText('Unspent · KES 2,410,000,000');
  await page.keyboard.press('Enter');
  await expect(spending).toHaveAttribute('aria-pressed', 'true');
  await page.keyboard.press('Escape');
  await expect(readout).toBeEmpty();
  await allocation.hover();
  await expect(readout).toHaveText('Allocated · KES 10,080,000,000');
  await allocation.tap();
  await panel.getByRole('heading', { name: 'Where the money went' }).tap();
  await expect(readout).toBeEmpty();

  await panel.getByText('Read chart data', { exact: true }).tap();
  await expect(panel.getByRole('row', { name: 'Reported procurement commitments KES 1,290,000,000' })).toBeVisible();
  await expect(panel.getByText(/Accounting scope is unconfirmed/)).toBeVisible();
  await expect(panel.getByText('No audit findings are recorded for FY2025/26 9M in this dataset.').first()).toBeVisible();
  await expect(panel.getByText(/No audit covers/)).toHaveCount(0);

  const source = panel.getByRole('button', { name: 'Source: Synthetic CBIRR nine-month budget review' });
  await source.tap();
  const dialog = page.getByRole('dialog', { name: 'Source and coverage' });
  await expect(dialog.getByRole('link', { name: fixture.source_document_title })).toHaveAttribute('href', fixture.source_document_url);
  await page.keyboard.press('Escape');
  await expect(source).toBeFocused();
  const historyLength = await page.evaluate(() => history.length);
  const origin = await page.evaluate(() => performance.timeOrigin);
  await panel.getByRole('button', { name: 'See Audit' }).tap();
  await expect(page.getByRole('tab', { name: 'Audit', exact: true })).toHaveAttribute('aria-selected', 'true');
  const url = new URL(page.url());
  expect(url.searchParams.get('tab')).toBe('audit');
  expect(url.searchParams.get('fy')).toBe('FY2024/25');
  expect(url.searchParams.getAll('keep')).toEqual(['one', 'two']);
  expect(url.hash).toBe('#record');
  expect(await page.evaluate(() => performance.timeOrigin)).toBe(origin);
  expect(await page.evaluate(() => history.length)).toBe(historyLength);
});

for (const [label, allocated, spent, expected] of [
  ['overspend', 10e9, 12e9, 'Reported spending exceeds the allocation by KES 2.00B in FY2025/26 9M.'],
  ['zero', 0, 0, 'The reported allocation and spending are zero in FY2025/26 9M.'],
  ['missing', null, 6e9, 'The allocation and spending comparison is unavailable for FY2025/26 9M.'],
] as const) {
  test(`keeps ${label} and partial audit amount coverage truthful`, async ({ page }) => {
    const coverage = { ...fixture.audit_amount_coverage, status: 'partial', reason: 'incomplete_amount_coverage',
      total_findings: 3, findings_with_amount: 1, findings_without_amount: 1, findings_with_invalid_amount: 1 };
    await page.route('**/api/v1/counties/001/money-flow?*', route => route.fulfill({ json: {
      ...fixture, audit_amount_coverage: coverage, committed_amount: null,
      stages: [
        { ...fixture.stages[0], amount: allocated, data_unavailable: allocated == null },
        { ...fixture.stages[1], amount: spent },
        { ...fixture.stages[2], amount: 0, data_unavailable: false },
      ],
    } }));
    await page.goto('/counties/001?tab=money');
    const panel = page.getByRole('tabpanel', { name: 'Money', exact: true });
    await expect(panel.getByText(expected)).toBeVisible();
    await expect(panel.getByText(/Partial subtotal: 1 of 3 cited findings/).first()).toBeVisible();
    await expect(panel.getByText(/Recorded finding amounts for .*KES 0/)).toBeVisible();
    await panel.getByText('Read chart data').tap();
    await expect(panel.getByRole('row', { name: /^Amounts in audit findings KES 0$/ })).toBeVisible();
    await expect(panel.getByText(/No audit covers/)).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}
