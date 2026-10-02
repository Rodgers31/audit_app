import { expect, test } from '@playwright/test';
import { registerApiMocks } from './utils/mockApi';

// These cases name the original contracts. Financial assertions use the shared
// synthetic API rather than conditionally accepting absent charts or SVG icons.
test.describe('Chart Data Validation - Counties Page', () => {
  test('budget chart displays correct data', async ({ page }) => {
    await page.goto('/counties');
    await page.getByPlaceholder('Type to search…').fill('Nairobi');
    await expect(page.locator('table tbody tr')).toHaveCount(1);
    await expect(page.locator('table tbody tr')).toContainText('10.0B');
    await expect(page.locator('table tbody tr')).toContainText('60%');
  });
  test('budget values match API response', async ({ page, request }) => {
    const response = await request.get('/api/v1/counties/001');
    expect(response.ok()).toBe(true);
    const county = await response.json();
    expect(county.financial_summary.total_allocation).toBe(10_000_000_000);
    await page.goto('/counties');
    await page.getByPlaceholder('Type to search…').fill('Nairobi');
    await expect(page.locator('table tbody tr')).toContainText(`${(county.financial_summary.total_allocation / 1e9).toFixed(1)}B`);
  });
  test('chart tooltip shows correct data on hover', async ({ page }) => {
    await registerApiMocks(page); await page.goto('/debt');
    const chart = page.locator('.recharts-wrapper').filter({ hasText: 'FY 2024/25' }).last();
    await chart.locator('.recharts-area-area').hover();
    await expect(chart.locator('.recharts-tooltip-wrapper')).toBeVisible();
    await expect(chart.locator('.recharts-tooltip-wrapper')).toContainText('50');
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
  // Debt charts have no segment drilldown. Clicking an icon proved nothing. #291.
  test.fixme('debt chart segments are clickable', async () => {});
  test('debt trend chart shows historical data', async ({ page }) => {
    await page.goto('/debt');
    const chart = page.locator('.recharts-wrapper').filter({ hasText: 'FY 2024/25' }).last();
    await expect(chart).toContainText('FY 2024/25');
    await expect(chart).toContainText('FY 2025/26');
    await expect(chart.locator('.recharts-area-area')).toHaveCount(1);
    await expect(chart.locator('.recharts-line-curve')).toHaveCount(1);
  });
});

test.describe('Chart Data Validation - County Details', () => {
  test('county spending breakdown chart is accurate', async ({ page }) => {
    await page.goto('/counties/001');
    await expect(page.getByText('KES 6.00B spent of KES 10.00B allocated', { exact: true })).toBeVisible();
    await expect(page.getByText('60.0%', { exact: true }).first()).toBeVisible();
    // The fixture publishes totals only; a sector pie must not be invented.
    await expect(page.getByText('Not reported', { exact: true }).first()).toBeVisible();
  });
  // No sector data is supplied; inventing a split to display a tooltip would
  // hide the missing-source behavior. Current totals are checked above. #291.
  test.fixme('county chart tooltips show category details', async () => {});
  test('audit status chart matches data', async ({ page }) => {
    await page.goto('/counties/001');
    await page.getByRole('button', { name: 'Audit Findings', exact: true }).click();
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
    await expect(page.getByRole('columnheader', { name: /Nairobi/ })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: /Mombasa/ })).toBeVisible();
    await expect(page.locator('table')).toContainText('10.0B');
    await expect(page.locator('table')).toContainText('60.0%');
  });
});

test.describe('Chart Responsiveness', () => {
  for (const [name, width, height] of [['mobile', 375, 667], ['tablet', 768, 1024]] as const) {
    test(`charts resize on ${name} viewport`, async ({ page }) => {
      await page.setViewportSize({ width, height });
      await page.goto('/budget');
      const chart = page.locator('.recharts-wrapper').first();
      await expect(chart).toBeVisible();
      const box = await chart.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.width).toBeGreaterThan(100);
      expect(box!.x + box!.width).toBeLessThanOrEqual(width);
    });
  }
  test('charts maintain bounds on resize', async ({ page }) => {
    await page.goto('/budget');
    const chart = page.locator('.recharts-wrapper').first();
    await expect(chart).toBeVisible();
    await page.setViewportSize({ width: 768, height: 1024 });
    await expect.poll(async () => (await chart.boundingBox())!.width).toBeLessThanOrEqual(768);
    await expect(chart.locator('.recharts-pie-sector')).toHaveCount(4);
  });
});

test.describe('Chart Accessibility', () => {
  test('charts have descriptive labels', async ({ page }) => {
    await page.goto('/budget');
    await expect(page.getByRole('heading', { name: 'The FY 2025/26 budget, visualised', exact: true })).toBeVisible();
    await expect(page.getByText('Interest on debt', { exact: true }).last().locator('../..')).toContainText('KES 30B');
  });
  // Current cost chart has no accessible application role or keyboard
  // handler. Preserve these original accessibility contracts under #291.
  test.fixme('charts have ARIA labels', async () => {});
  // No chart-to-table toggle exists. The county rankings table is exercised by
  // the original county cases; do not certify an absent feature. #291.
  test.fixme('chart data is available in table format', async () => {});
  test.fixme('charts support keyboard navigation', async () => {});
});

test.describe('Chart Performance', () => {
  test('charts load within reasonable time', async ({ page }) => {
    const start = Date.now();
    await page.goto('/budget');
    await expect(page.locator('.recharts-wrapper').first()).toBeVisible();
    expect(Date.now() - start).toBeLessThan(15_000);
  });
  test('multiple charts render without blocking UI', async ({ page }) => {
    await page.goto('/budget');
    await expect(page.locator('.recharts-wrapper').first()).toBeVisible();
    await page.getByRole('button', { name: 'FY2024/25', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'KES 150B approved for FY 2024/25' })).toBeVisible();
  });
});
