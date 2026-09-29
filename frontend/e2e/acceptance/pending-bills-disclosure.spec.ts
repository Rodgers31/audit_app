import { expect, Page, test } from '@playwright/test';
import type { PendingBillsResponse, PendingBillsSource, PendingBillsSummaryResponse } from '../../lib/api/debt';

const partialCoverage = {
  national_components: 2, national_expected: 2, national_complete: true,
  county_count: 46, county_expected: 47, county_complete: false,
  missing_counties: ['Nandi'], qualified_counties: [],
};

const sources: PendingBillsSource[] = [
  { side: 'national', title: 'Treasury BROP', url: 'https://example.org/brop', as_at: '2025-06-30' },
  { side: 'county', title: 'Controller of Budget CBIRR', url: 'https://example.org/cbirr', as_at: '2026-06-30' },
];

const partialBills: PendingBillsResponse = {
  status: 'success', data_source: 'database', pending_bills: [],
  summary: {
    total_pending: null, national_total: 525_900_000_000, county_total: null,
    total_absent_reason: 'incomplete_county_publication',
    reported_county_sum: 280_000_000_000, coverage: partialCoverage,
    national_as_at: '2025-06-30', county_as_at: '2026-06-30', record_count: 48,
  },
  sources, source: 'Treasury BROP; Controller of Budget CBIRR', source_url: sources[0].url,
  currency: 'KES', explanation: 'Synthetic fixture.',
};

const partialRanking: PendingBillsSummaryResponse = {
  total_pending_amount: null,
  total_absent_reason: 'incomplete_county_publication',
  reported_county_sum: 280_000_000_000, coverage: partialCoverage,
  breakdown_by_type: {}, aging_buckets: null,
  aging_buckets_absent_reason: 'loans_table_carries_no_aging_data', trend: [],
  top_counties_by_amount: [
    { county_id: '1', county_name: 'Mombasa', amount: 12_000_000_000, per_capita: 0, population: 0 },
  ],
};

async function fixturePage(
  page: Page,
  bills: PendingBillsResponse = partialBills,
  ranking: PendingBillsSummaryResponse = partialRanking,
) {
  // The SSR fixture API returns a no-data response. Make that dehydrated query
  // stale in the browser, so the real hook reads these intercepted fixtures.
  await page.clock.install({ time: new Date(Date.now() + 2 * 60 * 60 * 1000) });
  await page.route('**/api/v1/debt/national', (route) => route.fulfill({ json: {
    status: 'success', data: {
      total_outstanding: 12_000_000_000_000, gdp: 20_000_000_000_000,
      categories: {}, summary: {},
    },
  } }));
  await page.route('**/api/v1/pending-bills/summary', (route) => route.fulfill({ json: ranking }));
  await page.route('**/api/v1/pending-bills', (route) => route.fulfill({ json: bills }));
  await page.goto('/debt');
  await expect(page.getByRole('heading', { name: 'Stalled payments' })).toBeVisible();
}

const completeCoverage = {
  ...partialCoverage, county_count: 47, county_complete: true, missing_counties: [],
};
const qualifiedCoverage = {
  ...partialCoverage, county_count: 47, missing_counties: [], qualified_counties: ['Nandi'],
};

for (const viewport of [
  { name: 'desktop', width: 1366, height: 900 },
  { name: 'narrow mobile', width: 360, height: 780 },
]) {
  test(`partial county disclosure at ${viewport.name} width`, async ({ page }, testInfo) => {
    await page.setViewportSize(viewport);
    await fixturePage(page);
    const section = page.getByRole('heading', { name: 'Stalled payments' }).locator('xpath=ancestor::section[1]');
    await expect(section).toContainText('Combined total not published');
    await expect(section).toContainText('46 of 47 counties');
    await expect(section).toContainText('Reported county sum: KES 280.0B');
    await expect(section).not.toContainText('KES 805.9B');
    await expect(section.getByRole('link', { name: 'Treasury BROP' })).toHaveAttribute('href', sources[0].url!);
    await expect(section.getByRole('link', { name: 'Controller of Budget CBIRR' })).toHaveAttribute('href', sources[1].url!);
    await expect(section).toContainText('30 June 2025');
    await expect(section).toContainText('30 June 2026');
    await section.getByRole('button', { name: 'Counties' }).click();
    await expect(section.getByRole('heading', { name: 'Reported counties by stalled payments' })).toBeVisible();
    await expect(section).toContainText('Ranking covers 46 of 47 counties with reported amounts.');
    expect(await section.evaluate((node) => node.scrollWidth <= node.clientWidth)).toBe(true);
    if (viewport.name === 'narrow mobile') {
      await section.screenshot({ path: testInfo.outputPath('partial-mobile-section.png') });
    }
  });

  test(`qualified county disclosure at ${viewport.name} width`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await fixturePage(page,
      { ...partialBills, summary: { ...partialBills.summary, coverage: qualifiedCoverage } },
      { ...partialRanking, coverage: qualifiedCoverage });
    const section = page.getByRole('heading', { name: 'Stalled payments' }).locator('xpath=ancestor::section[1]');
    await expect(section).toContainText('qualified reported amounts');
    await expect(section).toContainText('Reported county sum: KES 280.0B');
    await section.getByRole('button', { name: 'Counties' }).click();
    await expect(section.getByRole('heading', { name: 'Reported counties by stalled payments' })).toBeVisible();
    await expect(section).toContainText('Ranking includes 1 county with qualified reported amounts.');
    expect(await section.evaluate((node) => node.scrollWidth <= node.clientWidth)).toBe(true);
  });

  test(`complete publication at ${viewport.name} width`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await fixturePage(page,
      { ...partialBills, summary: {
        ...partialBills.summary, total_pending: 805_900_000_000, county_total: 280_000_000_000,
        total_absent_reason: null, coverage: completeCoverage, county_as_at: '2025-06-30',
      }, sources: [sources[0], { ...sources[1], as_at: '2025-06-30' }] },
      { ...partialRanking, total_pending_amount: 805_900_000_000,
        total_absent_reason: null, coverage: completeCoverage });
    const section = page.getByRole('heading', { name: 'Stalled payments' }).locator('xpath=ancestor::section[1]');
    await expect(section).toContainText('KES 805.9B');
    await expect(section).toContainText('KES 280.0B');
    await expect(section).not.toContainText('Combined total not published');
    await expect(section.getByRole('link', { name: 'Controller of Budget CBIRR' })).toHaveAttribute('href', sources[1].url!);
    await section.getByRole('button', { name: 'Counties' }).click();
    await expect(section.getByRole('heading', { name: 'Top counties by stalled payments' })).toBeVisible();
    expect(await section.evaluate((node) => node.scrollWidth <= node.clientWidth)).toBe(true);
  });

  test(`explicit published zero at ${viewport.name} width`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await fixturePage(page,
      { ...partialBills, summary: {
        ...partialBills.summary, total_pending: 0, national_total: 0, county_total: 0,
        reported_county_sum: 0, total_absent_reason: null, coverage: completeCoverage,
        county_as_at: '2025-06-30',
      }, sources: [sources[0], { ...sources[1], as_at: '2025-06-30' }] },
      { ...partialRanking, total_pending_amount: 0, reported_county_sum: 0,
        total_absent_reason: null, coverage: completeCoverage, top_counties_by_amount: [] });
    const section = page.getByRole('heading', { name: 'Stalled payments' }).locator('xpath=ancestor::section[1]');
    await expect(section).toContainText('KES 0');
    await expect(section).not.toContainText('Combined total not published');
    expect(await section.evaluate((node) => node.scrollWidth <= node.clientWidth)).toBe(true);
  });

  test(`missing publication at ${viewport.name} width`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await fixturePage(page,
      { ...partialBills, status: 'no_data', summary: {
        total_pending: null, national_total: null, county_total: null, record_count: 0,
      } },
      { ...partialRanking, top_counties_by_amount: [] });
    const section = page.getByRole('heading', { name: 'Stalled payments' }).locator('xpath=ancestor::section[1]');
    await expect(section).toContainText('No pending-bills figure is published here.');
    await expect(section).not.toContainText('KES 0');
    expect(await section.evaluate((node) => node.scrollWidth <= node.clientWidth)).toBe(true);
  });
}
