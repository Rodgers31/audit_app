import { expect, test } from '@playwright/test';
import { registerApiMocks } from './utils/mockApi';

// These cases name the original contracts. Financial assertions use the shared
// synthetic API rather than conditionally accepting absent charts or SVG icons.
test.describe('Chart Data Validation - Counties Page', () => {
  test('budget chart displays correct data', async ({ page }) => {
    await page.goto('/counties?layout=table');
    await page.getByPlaceholder('Type to search…').fill('Nairobi');
    await expect(page.locator('table tbody tr')).toHaveCount(1);
    await expect(page.locator('table tbody tr')).toContainText('10.0B');
    await expect(page.getByRole('cell', { name: 'No published rate' })).toBeVisible();
  });
  test('budget values match API response', async ({ page, request }) => {
    const response = await request.get('/api/v1/counties/001');
    expect(response.ok()).toBe(true);
    const county = await response.json();
    expect(county.financial_summary.total_allocation).toBe(10_000_000_000);
    await page.goto('/counties?layout=table');
    await page.getByPlaceholder('Type to search…').fill('Nairobi');
    await expect(page.locator('table tbody tr')).toContainText(`${(county.financial_summary.total_allocation / 1e9).toFixed(1)}B`);
  });
  test('debt cost hover shows both published measures for the same year', async ({ page }) => {
    await registerApiMocks(page);
    await page.goto('/debt');
    const figure = page.getByRole('figure', { name: 'The cost of debt over time', exact: true });
    const ratio = figure.getByRole('button', { name: /FY 2024\/25 · Shillings of every KES 100 in revenue · KES 50$/ });
    await ratio.hover();
    await expect(figure.getByRole('status')).toHaveText('FY 2024/25 · Debt repayments KES 50,000,000,000 · KES 50 of every KES 100');
    await expect(figure.locator('[data-debt-cost-guide]')).toHaveCount(2);
  });
  // Counties now has a rankings table/map, not a togglable chart legend. #291.
  test.fixme('chart legend is interactive', async () => {});
});

test.describe('Chart Data Validation - Debt Page', () => {
  test.beforeEach(async ({ page }) => { await registerApiMocks(page); });
  test('debt composition preserves absence without a loan register', async ({ page }) => {
    await page.goto('/debt');
    await expect(page.getByRole('heading', { name: 'Who Kenya owes', exact: true })).toBeVisible();
    await expect(page.getByText('No lender breakdown available yet.', { exact: true })).toBeVisible();
  });
  test('debt values are formatted correctly', async ({ page }) => {
    await page.goto('/debt');
    await expect(page.getByText('KES 12.00T', { exact: true })).toBeVisible();
    await expect(page.getByText('Debt-to-GDP', { exact: true }).locator('..')).toContainText('60.0%');
  });
  test('debt trend charts align their fiscal years and keep one measure in each chart', async ({ page }) => {
    await page.goto('/debt');
    const figure = page.getByRole('figure', { name: 'The cost of debt over time', exact: true });
    await expect(figure.getByRole('img')).toHaveCount(2);
    for (const year of ['FY 2024/25', 'FY 2025/26']) {
      await expect(figure.getByRole('button', { name: `${year} · Debt repayments · KES 50,000,000,000`, exact: true })).toBeVisible();
      await expect(figure.getByRole('button', { name: `${year} · Shillings of every KES 100 in revenue · KES 50`, exact: true })).toBeVisible();
    }
    await expect(figure.locator('[data-debt-share-line]')).toHaveAttribute('d', 'M0.5,50 L1.5,50');
    await expect(figure.getByText('Half of revenue (50)', { exact: true })).toBeVisible();
  });
  test('mobile debt chart labels stay under their fiscal years when intermediate labels are hidden', async ({ page, request }) => {
    await page.setViewportSize({ width: 360, height: 860 });
    const response = await request.get('/api/v1/fiscal/summary');
    expect(response.ok()).toBe(true);
    const fiscal = await response.json();
    const reference = fiscal.current;
    const history = Array.from({ length: 5 }, (_, index) => ({
      ...reference,
      fiscal_year: `FY ${2021 + index}/${22 + index}`,
      debt_service_per_shilling: index === 2 ? null : reference.debt_service_per_shilling,
    }));
    await page.clock.setFixedTime(new Date(Date.now() + 2 * 60 * 60 * 1000));
    await page.route('**/api/v1/fiscal/summary', route => route.fulfill({
      json: { ...fiscal, history, current: history[4], total_fiscal_years: history.length },
    }));
    await page.goto('/debt');
    const figure = page.getByRole('figure', { name: 'The cost of debt over time', exact: true });
    for (const year of ['2021/22', '2023/24', '2025/26']) {
      const label = figure.getByText(`FY${year.slice(2)}`, { exact: true }).filter({ visible: true });
      const target = figure.getByRole('button', { name: new RegExp(`^FY ${year} · Shillings`) });
      await expect(label).toBeVisible();
      await expect(target).toBeVisible();
      const center = (rect: { x: number; width: number }) => rect.x + rect.width / 2;
      expect(Math.abs(center((await label.boundingBox())!) - center((await target.boundingBox())!))).toBeLessThan(1);
    }
    await expect(figure.locator('[data-debt-share-line]')).toHaveAttribute('d', 'M0.5,50 L1.5,50 M3.5,50 L4.5,50');
    await expect(figure.getByRole('button', { name: /^FY 2023\/24 · Shillings.*Not published$/ })).toBeVisible();
  });
});

test.describe('Chart Data Validation - County Details', () => {
  test('county budget shows exact totals and preserves the missing breakdown', async ({ page }) => {
    await page.goto('/counties/001?tab=budget');
    const budget = page.getByRole('tabpanel', { name: 'Budget', exact: true });
    await expect(budget.getByText('KES 10.00B', { exact: true })).toBeVisible();
    await expect(budget.getByText('KES 6.00B', { exact: true })).toBeVisible();
    await expect(budget.getByText('60.0% execution', { exact: true })).toBeVisible();

    // The fixture publishes totals only.
    await expect(budget.getByText('Not classified in source data', { exact: true })).toHaveCount(2);
    await expect(budget.getByRole('heading', { name: 'Sector Spending', exact: true })).toHaveCount(0);
  });
  // No sector data is supplied; inventing a split to display a tooltip would
  // hide the missing-source behavior. Current totals are checked above. #291.
  test.fixme('county chart tooltips show category details', async () => {});
  test('audit status chart matches data', async ({ page }) => {
    await page.goto('/counties/001');
    await page.getByRole('tab', { name: 'Audit', exact: true }).click();
    await expect(page.locator('main')).toContainText('Synthetic browser finding');
    await expect(page.locator('main')).toContainText('Kshs.1,000,000.');
    await expect(page.getByRole('link', { name: 'Source report, p. 2' }).first()).toHaveAttribute('href', /example\.invalid.*#page=2$/);
  });
});

test.describe('Chart Interactivity', () => {
  // Named quarantines of controls that do not exist in the shipped charts.
  // Tracking #291; preserve follow-up ownership before closing its parent.
  test.fixme('chart zoom controls work', async () => {});
  test('chart can be exported or downloaded', async ({ page }) => {
    await registerApiMocks(page);
    await page.goto('/debt');
    // The original contract checks the visible export control. Browser printing
    // is a supported PDF export; a network download is not required.
    await expect(page.getByRole('button', { name: 'Export PDF', exact: true })).toBeVisible();
  });
  test('chart time range selector works', async ({ page }) => {
    await page.goto('/budget');
    await expect(page.getByRole('heading', { name: 'KES 180B approved for FY 2025/26' })).toBeVisible();
    await page.getByRole('button', { name: 'FY2024/25', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'KES 150B approved for FY 2024/25' })).toBeVisible();
  });
  test('chart comparison mode works', async ({ page }) => {
    await page.goto('/counties/compare?ids=001,047');
    const comparison = page.getByRole('table', { name: 'County comparison', exact: true });
    await expect(comparison.getByRole('columnheader', { name: /Nairobi/ })).toBeVisible();
    await expect(comparison.getByRole('columnheader', { name: /Mombasa/ })).toBeVisible();
    await expect(comparison).toContainText('10.0B');
    await expect(comparison).toContainText('60.0%');
  });
});

test.describe('Chart Responsiveness', () => {
  for (const [name, width, height] of [['mobile', 375, 667], ['tablet', 768, 1024]] as const) {
    test(`charts resize on ${name} viewport`, async ({ page }) => {
      await page.setViewportSize({ width, height });
      await page.goto('/budget');
      const chart = page.getByRole('button', { name: 'Explore Where it goes', exact: true });
      await expect(chart).toBeVisible();
      const box = await chart.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.width).toBeGreaterThan(100);
      expect(box!.x + box!.width).toBeLessThanOrEqual(width);
    });
  }
  test('charts maintain bounds on resize', async ({ page }) => {
    await page.goto('/budget');
    const chart = page.getByRole('button', { name: 'Explore Where it goes', exact: true });
    await expect(chart).toBeVisible();
    await page.setViewportSize({ width: 768, height: 1024 });
    await expect.poll(async () => (await chart.boundingBox())!.width).toBeLessThanOrEqual(768);
    await expect(chart.locator('..').locator('[aria-hidden=true] > [data-segment]')).toHaveCount(4);
  });
});

test.describe('Chart Accessibility', () => {
  test('charts have descriptive labels', async ({ page }) => {
    await page.goto('/budget');
    const uses = page.getByRole('region', { name: 'Where it goes' });
    await expect(uses.getByRole('button', { name: 'Interest on debt KES 30B' })).toBeVisible();
    await uses.getByText('Read chart data', { exact: true }).click();
    await expect(uses.getByRole('row', { name: /Interest on debt/ })).toContainText('KES 30,000,000,000 · 20%');
  });
  test('charts have ARIA labels', async ({ page }) => {
    await registerApiMocks(page); await page.goto('/debt');
    const figure = page.getByRole('figure', { name: 'The cost of debt over time', exact: true });
    await expect(figure).toBeVisible();
    await expect(figure).toHaveAccessibleDescription(/Annual debt service.*share of revenue.*Read chart data/);
    await expect(figure.getByRole('img', { name: 'Debt repayments in KES by fiscal year', exact: true })).toBeVisible();
    await expect(figure.getByRole('img', { name: /Repayments per KES 100 of ordinary revenue by fiscal year.*half of revenue/ })).toBeVisible();
  });
  test('chart data is available in table format', async ({ page }) => {
    await registerApiMocks(page); await page.goto('/debt');
    const figure = page.getByRole('figure', { name: 'The cost of debt over time', exact: true });
    await figure.locator('summary').click();
    const table = figure.getByRole('table', { name: 'Debt cost observations by fiscal year', exact: true });
    await expect(table).toBeVisible();
    await expect(table.getByRole('columnheader')).toHaveText(['Fiscal year', 'Debt service (KES)', 'Revenue (KES)', 'Service / revenue (%)']);
    // Independently supplied fixture API values, not values derived from the UI.
    const rows = table.locator('tbody tr');
    await expect(rows).toHaveCount(2);
    for (const year of ['FY 2024/25', 'FY 2025/26']) {
      const row = rows.filter({ has: page.getByRole('rowheader', { name: year, exact: true }) });
      await expect(row.getByRole('rowheader')).toHaveText(year);
      await expect(row.getByRole('cell')).toHaveText([
        /^50,000,000,000Approved ·/, /^100,000,000,000Approved ·/, '50.0%',
      ]);
      await expect(row.getByRole('link', { name: 'Synthetic browser fiscal framework · p. 1' })).toHaveCount(2);
    }
  });
  test('debt charts and their data disclosure support keyboard navigation', async ({ page, browserName }) => {
    await registerApiMocks(page);
    await page.goto('/debt');
    const figure = page.getByRole('figure', { name: 'The cost of debt over time', exact: true });
    const first = figure.getByRole('button', { name: /^FY 2024\/25 · Debt repayments/ });
    await first.focus();
    await expect(figure.getByRole('status')).toContainText('FY 2024/25');
    await page.keyboard.press('Enter');
    await expect(first).toHaveAttribute('aria-pressed', 'true');
    await page.keyboard.press('Escape');
    await expect(first).toBeFocused();
    await expect(first).toHaveAttribute('aria-pressed', 'false');
    // macOS WebKit uses Option+Tab to include all controls by default.
    await page.keyboard.press(browserName === 'webkit' ? 'Alt+Tab' : 'Tab');
    await expect(figure.getByRole('button', { name: /^FY 2025\/26 · Debt repayments/ })).toBeFocused();
    await expect(figure.getByRole('status')).toContainText('KES 50 of every KES 100');
    const summary = figure.locator('summary');
    await summary.focus();
    await page.keyboard.press('Enter');
    await expect(figure.getByRole('table', { name: 'Debt cost observations by fiscal year' })).toBeVisible();
    await page.keyboard.press('Space');
    await expect(figure.getByRole('table')).toBeHidden();
    await page.keyboard.press(browserName === 'webkit' ? 'Alt+Tab' : 'Tab');
    await expect(summary).not.toBeFocused();
  });
});

test.describe('Chart Performance', () => {
  test('charts load within reasonable time', async ({ page }) => {
    const start = Date.now();
    await page.goto('/budget');
    await expect(page.getByRole('button', { name: 'Explore Where it goes', exact: true })).toBeVisible();
    expect(Date.now() - start).toBeLessThan(15_000);
  });
  test('multiple charts render without blocking UI', async ({ page }) => {
    await page.goto('/budget');
    await expect(page.getByRole('button', { name: 'Explore Where it goes', exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'FY2024/25', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'KES 150B approved for FY 2024/25' })).toBeVisible();
  });
});
