import { expect, test } from '@playwright/test';
import nationalObservation from './fixtures/debt_overview.json';
import lenderGroups from './fixtures/debt_lender_groups.json';
import { registerApiMocks } from './utils/mockApi';

test.beforeEach(async ({ page }) => { await registerApiMocks(page); });

type HeadlineFrame = { amount: string; visible: boolean };

declare global {
  interface Window {
    debtHeadlineFrames?: HeadlineFrame[];
  }
}

test('the first client frame shows the sourced national debt total', async ({ page }) => {
  // The fixture API refuses the SSR prefetch in this cohort. Observe the first
  // client commit after the browser receives the separate mocked loan balance.
  await page.addInitScript(() => {
    const frames: HeadlineFrame[] = [];
    window.debtHeadlineFrames = frames;
    new MutationObserver(() => {
      const amount = document.querySelector('[data-testid="national-debt-outstanding"]');
      if (!amount) return;
      const frame = {
        amount: amount.textContent?.replace(/\s+/g, ' ').trim() ?? '',
        visible: amount.checkVisibility({ opacityProperty: true, visibilityProperty: true }),
      };
      const previous = frames.at(-1);
      if (frame.amount !== previous?.amount || frame.visible !== previous.visible) frames.push(frame);
    }).observe(document, { childList: true, subtree: true, characterData: true, attributes: true });
  });
  await page.goto('/debt');
  const expected = `KES ${(nationalObservation.data.total_outstanding / 1e12).toFixed(2)}T`;
  await expect(page.getByTestId('national-debt-outstanding')).toHaveText(expected);
  await expect(page.getByText('Balance date unavailable', { exact: true })).toBeVisible();
  await expect(page.getByText('Live national debt counter', { exact: true })).toHaveCount(0);
  expect(await page.evaluate(() => window.debtHeadlineFrames)).toEqual([
    { amount: expected, visible: true },
  ]);
});

test('a missing outstanding balance does not become the principal or a guessed date', async ({ page }) => {
  await page.route('**/api/v1/debt/national', route => route.fulfill({ json: {
    ...nationalObservation,
    last_updated: '2026-08-15T00:00:00',
    data: { ...nationalObservation.data, total_outstanding: null, total_debt: 12_000_000_000_000 },
  } }));
  await page.goto('/debt');
  await expect(page.getByTestId('national-debt-outstanding')).toHaveText('Debt total unavailable');
});

test('a failed debt snapshot can be retried without a substitute figure', async ({ page }) => {
  let available = false;
  await page.route('**/api/v1/debt/national', route => available
    ? route.fulfill({ json: nationalObservation })
    : route.fulfill({ status: 503, json: { status: 'unavailable' } }));
  await page.goto('/debt');
  await expect(page.getByRole('heading', { name: 'Failed to load debt data' })).toBeVisible();
  await expect(page.getByTestId('national-debt-outstanding')).toHaveCount(0);
  available = true;
  await page.getByRole('button', { name: 'Retry fetch' }).click();
  await expect(page.getByTestId('national-debt-outstanding')).toHaveText('KES 12.00T');
});

test('national debt page shows key stats and charts', async ({ page }) => {
  await page.goto('/debt');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText("Kenya's National Debt");
  const ratio = page.getByText('Debt-to-GDP', { exact: true }).locator('..');
  await expect(ratio).toContainText('60.0%');
  await expect(ratio).toContainText('IMF World Economic Outlook');
  await expect(ratio).toContainText('Observation: 2025');
  await expect(page.getByText('Not assessed', { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'The cost of debt over time' })).toBeVisible();
  await expect(page.locator('.recharts-wrapper').first()).toBeVisible();
});

test('"Where every KES 100" card uses the synthetic fiscal-summary ratio (50, tax + non-tax revenue)', async ({ page }) => {
  await page.goto('/debt');
  await expect(page.getByRole('heading', { name: /Where every KES 100 of revenue goes/i })).toBeVisible();
  await expect(page.getByTestId('debt-headline-kes')).toHaveText('50');
  await expect(page.getByText(/Debt service takes about/i)).toBeVisible();
  await expect(page.getByText(/Spending per KES 100 of revenue: 150\.0/i)).toBeVisible();
  await expect(page.getByText(/The 50\.0 above 100 is financed by A-i-A \(20\.0\), grants \(5\.0\), net borrowing \(25\.0\)/i)).toBeVisible();
});

test('debt page exposes a methodology disclosure with the total-debt-service calculation', async ({ page }) => {
  await page.goto('/debt');
  const summary = page.getByText('How this is calculated', { exact: true });
  await summary.click();
  const disclosure = summary.locator('..');
  await expect(disclosure).toContainText('50');
  await expect(disclosure).toContainText(/interest|principal/i);
  await expect(disclosure).toContainText(/Different official debt-service measures/i);
});

test('debt page does not undermine the headline with discouraging copy', async ({ page }) => {
  await page.goto('/debt');
  // Establish that the card actually rendered before testing absent wording.
  await expect(page.getByTestId('debt-headline-kes')).toHaveText('50');
  for (const text of [/actual number is higher/i, /real number is higher/i, /this number is incomplete/i]) {
    await expect(page.getByText(text)).toHaveCount(0);
  }
});

test('debt page source line names the ratio inputs explicitly', async ({ page }) => {
  await page.goto('/debt');
  await expect(page.getByText(/Uses tax & non-tax revenue; debt figure includes total debt service/i)).toContainText('(interest + principal redemptions)');
  await expect(page.getByText(/FY 2025\/26 debt service is from Synthetic local fixture/))
    .toContainText('Synthetic browser fiscal framework (p. 1)');
});

test.describe('ranked lender groups', () => {
  test.use({ hasTouch: true, viewport: { width: 360, height: 820 }, reducedMotion: 'reduce' });

  test('ranks every group, opens full lender names and preserves the published tail', async ({ page }) => {
    await page.route('**/api/v1/debt/national', route => route.fulfill({ json: {
      ...nationalObservation,
      data: { ...nationalObservation.data, categories: lenderGroups },
    } }));
    await page.goto('/debt');
    const section = page.getByRole('region', { name: 'Who Kenya owes' });
    await expect(section.getByText('Domestic lenders hold more than half of the debt shown (55%).')).toBeVisible();
    const ranking = section.getByRole('list').nth(1);
    const categories = ranking.getByRole('button');
    await expect(categories).toHaveCount(5);
    await expect(categories.first()).toContainText('Domestic bonds');
    await expect(categories.nth(1)).toContainText('World Bank and other multilaterals');
    await expect(categories.nth(2)).toContainText('Eurobonds and commercial loans');
    await expect(section.locator('.recharts-wrapper')).toHaveCount(0);

    const multilaterals = section.getByRole('button', { name: /World Bank and other multilaterals/ });
    await multilaterals.focus();
    await page.keyboard.press('Enter');
    await expect(multilaterals).toHaveAttribute('aria-expanded', 'true');
    await expect(section.getByText('World Bank International Development Association', { exact: true })).toBeVisible();
    await expect(section.getByText('Synthetic ninth named lender with an intentionally long full name', { exact: true })).toBeVisible();
    const tail = section.getByText('Other lenders (4 reported)', { exact: true }).locator('..');
    await expect(tail).toContainText('KES 400,000,000,000');
    await page.keyboard.press('Space');
    await expect(multilaterals).toHaveAttribute('aria-expanded', 'false');

    const more = section.getByRole('button', { name: 'Show 2 more groups', exact: true });
    await more.tap();
    await expect(categories).toHaveCount(7);
    await expect(categories.nth(5)).toBeFocused();
    const unclassified = section.getByRole('button', { name: /Future External Lenders/ });
    await expect(unclassified).toContainText('Lender type unclassified');
    await unclassified.tap();
    await expect(section.getByText('Individual lenders are unavailable for this group.')).toBeVisible();
    await expect(section.getByText(/Shares use the KES 13\.00T total of the lender groups shown/)).toBeVisible();
    await expect(section.getByRole('button', { name: /pending bills/i })).toHaveCount(0);
  });
});

test('gives separate commercial loans and Eurobonds their own labels when both are reported', async ({ page }) => {
  await page.route('**/api/v1/debt/national', route => route.fulfill({ json: {
    ...nationalObservation,
    data: { ...nationalObservation.data, categories: {
      external_commercial: { total_outstanding: 160 },
      external_eurobond: { total_outstanding: 40 },
    } },
  } }));
  await page.goto('/debt');
  const section = page.getByRole('region', { name: 'Who Kenya owes' });
  await expect(section.getByRole('button', { name: /^Commercial loans/ })).toBeVisible();
  await expect(section.getByRole('button', { name: /^Eurobonds/ })).toBeVisible();
  await expect(section.getByRole('button', { name: /Eurobonds and commercial loans/ })).toHaveCount(0);
});

test('discloses the basis of principal-only amounts and keeps small positive shares legible', async ({ page }) => {
  await page.route('**/api/v1/debt/national', route => route.fulfill({ json: {
    ...nationalObservation,
    data: { ...nationalObservation.data, categories: {
      domestic_bonds: { total_outstanding: 9980 },
      future_external_lenders: {
        total_principal: 20,
        items: [{ lender: 'Synthetic lender with a zero balance', outstanding: 0 }],
        other_lender_count: 3,
        items_truncated: true,
      },
    } },
  } }));
  await page.goto('/debt');
  const section = page.getByRole('region', { name: 'Who Kenya owes' });
  await expect(section.getByText('The largest group is Domestic bonds, with 99.8% of the amounts shown.')).toBeVisible();
  await expect(section.getByText('Groups labeled original principal use the loan amount originally recorded.')).toBeVisible();
  await expect(section.getByText(/Shares use the KES 10,000 total of the amounts shown/)).toBeVisible();
  const small = section.getByRole('button', { name: /Future External Lenders/ });
  await expect(small).toContainText('0.2% · Lender type unclassified · Original principal');
  await small.click();
  await expect(section.getByText('Synthetic lender with a zero balance').locator('..')).toContainText('KES 0');
  await expect(section.getByText('Other lenders (3 reported)').locator('..')).toContainText('Amount unavailable');
});

const loanRateSource = { title: 'Synthetic CBK rates', url: 'https://example.test/rates', as_of: '2026-10-15' };
const registerRow = (id: number, lender: string, lender_type: string, outstanding_numeric: number, fields = {}) => ({
  record_id: id,
  lender,
  lender_type,
  outstanding_numeric,
  interest_rate_pct: null as number | null,
  annual_service_cost: null as number | null,
  maturity_date: '',
  ...fields,
});
const longLender = 'Multilateral (Eastern and Southern African Trade and Development Bank)';
const loanRows = [
  registerRow(201, 'Domestic Treasury Bonds', 'domestic_bonds', 600e9, {
    interest_rate_pct: 13.46,
    interest_rate_basis: 'coupon_weighted_average',
    interest_rate_label: 'Published reference covers 57% of the bond stock.',
    interest_rate_source: loanRateSource,
    annual_service_basis: 'modelled',
    annual_service_cost: 60e9,
    qualifications: {
      interest_rate: {
        status: 'conflicting', reason: 'conflicting_reporting_dates', publisher: 'Synthetic Central Bank',
        source_url: loanRateSource.url, source_kind: 'document',
        identity: { measure: 'interest_rate', geography: 'national', period: '2026', unit: 'percent', basis: 'actual' },
      },
    },
  }),
  registerRow(202, longLender, 'external_multilateral', 500e9, {
    annual_service_basis: 'published', annual_service_cost: 70e9, annual_service_label: 'Interest paid in 2024',
    maturity_date: '2044-12-31',
  }),
  registerRow(203, 'Commercial Bank label only', 'domestic_overdraft', 400e9),
  registerRow(204, 'Bilateral external test', 'external_bilateral', 300e9),
  registerRow(205, 'Domestic Treasury Bills', 'domestic_bills', 200e9, {
    interest_rate_pct: 8.75, interest_rate_basis: 'auction_yield', interest_rate_source: loanRateSource,
  }),
  registerRow(206, 'External Commercial Bank', 'external_commercial', 100e9, {
    interest_rate_pct: 99, interest_rate_basis: 'auction_yield',
    annual_service_basis: 'published', annual_service_cost: 0, annual_service_label: 'Interest paid in 2024',
  }),
  registerRow(207, 'Other Domestic Debt', 'other', 90e9),
  ...Array.from({ length: 4 }, (_, index) => registerRow(208 + index, `Bilateral fixture ${index}`, 'external_bilateral', 80e9 - index)),
  registerRow(212, 'Multilateral lender beyond initial list', 'external_multilateral', 50e9),
];

test('loan register searches matching groups over the full collection and retains readable mobile cards', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 840 });
  await page.clock.setFixedTime(new Date(Date.now() + 2 * 60 * 60 * 1000));
  await page.route('**/api/v1/debt/loans', route => route.fulfill({ json: { loans: loanRows } }));
  await page.goto('/debt#loan-register');

  const register = page.getByRole('region', { name: 'The full loan register' });
  const cards = register.getByRole('list', { name: 'The full loan register' }).getByRole('listitem');
  await expect(register.getByRole('status')).toHaveText('Showing 10 of 12 matching lines');
  await expect(cards).toHaveCount(10);
  const name = cards.nth(1).getByText(longLender, { exact: true });
  expect(await name.evaluate(element => element.getBoundingClientRect().height > parseFloat(getComputedStyle(element).lineHeight) * 1.5)).toBe(true);
  await expect(register.getByRole('table')).toHaveCount(0);

  const showAll = register.getByRole('button', { name: 'Show all 12 matching lines' });
  await showAll.click();
  await expect(cards).toHaveCount(12);
  const showFirst = register.getByRole('button', { name: 'Show the first 10 lines' });
  await expect(showFirst).toHaveAttribute('aria-expanded', 'true');
  await showFirst.click();

  const search = register.getByRole('searchbox', { name: 'Search lender names' });
  await search.fill('   BEYOND   INITIAL  ');
  await expect(cards).toHaveCount(1);
  await expect(cards.first()).toContainText('Multilateral lender beyond initial list');

  const domestic = register.getByRole('button', { name: 'Domestic', exact: true });
  await domestic.click();
  await expect(domestic).toHaveAttribute('aria-pressed', 'true');
  await expect(register.getByText('No register lines match these filters.')).toBeVisible();
  await register.getByRole('button', { name: 'Clear search and filter' }).click();
  await expect(search).toBeFocused();
  await expect(register.getByRole('button', { name: 'All', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(cards.getByText('Other Domestic Debt', { exact: true })).toBeVisible();

  await domestic.click();
  await expect(cards).toHaveCount(3);
  await expect(cards.getByText('Other Domestic Debt', { exact: true })).toHaveCount(0);
  await expect(cards.getByText('Commercial Bank label only', { exact: true })).toBeVisible();
  for (const [group, count] of [['Multilateral', 2], ['Bilateral', 5], ['Commercial', 1]] as const) {
    await register.getByRole('button', { name: group, exact: true }).click();
    await expect(cards).toHaveCount(count);
  }
  expect(await register.evaluate(element => element.scrollWidth)).toBe(await register.evaluate(element => element.clientWidth));
});

test('loan register sorts the table and keeps published reference rates, absences and evidence distinct', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 840 });
  await page.clock.setFixedTime(new Date(Date.now() + 2 * 60 * 60 * 1000));
  await page.route('**/api/v1/debt/loans', route => route.fulfill({ json: { loans: loanRows.slice(0, 7).reverse() } }));
  await page.goto('/debt#loan-register');

  const register = page.getByRole('region', { name: 'The full loan register' });
  const table = register.getByRole('table');
  const rows = table.getByRole('row').filter({ has: page.getByRole('cell') });
  await expect(rows.first()).toContainText('Domestic Treasury Bonds');
  await expect(table.getByRole('columnheader', { name: 'Outstanding' })).toHaveAttribute('aria-sort', 'descending');

  const sort = register.getByRole('combobox', { name: 'Sort by' });
  await sort.selectOption('rate');
  await expect(table.getByRole('columnheader', { name: 'Interest rate', exact: true })).toHaveAttribute('aria-sort', 'descending');
  await expect(rows.first()).toContainText('13.46%');
  await expect(rows.first()).toContainText('Conflicting evidence');
  await expect(rows.nth(1)).toContainText('91-day Treasury bill yield');
  const misleadingRate = rows.filter({ hasText: 'External Commercial Bank' });
  await expect(misleadingRate.getByRole('cell', { name: 'Not published', exact: true })).toBeVisible();
  await expect(misleadingRate.getByText('99.00%')).toHaveCount(0);
  await expect(misleadingRate.getByRole('cell', { name: 'KES 0 Paid 2024' })).toBeVisible();
  await expect(rows.first().getByRole('link', { name: 'Weighted coupon average' })).toHaveAttribute('href', 'https://example.test/rates');

  const source = rows.first().getByRole('button', { name: /Synthetic Central Bank.*Domestic Treasury Bonds/ });
  await source.click();
  const dialog = page.getByRole('dialog', { name: 'Where this figure comes from' });
  await expect(dialog.getByText(/Published reference covers 57% of the bond stock/)).toContainText('Rate source date 2026-10-15.');
  await expect(dialog.getByRole('link', { name: 'Observation evidence details' })).toHaveAttribute('href', '/sources/figures/loans/201');
  await dialog.press('Escape');
  await expect(source).toBeFocused();

  await sort.selectOption('service');
  await expect(table.getByRole('columnheader', { name: 'Annual interest' })).toHaveAttribute('aria-sort', 'descending');
  await expect(rows.first()).toContainText('Paid 2024');
  await expect(rows.first()).toContainText('2044-12-31');
  await expect(rows.nth(1)).toContainText('Modelled');
  await expect(rows.nth(2)).toContainText('External Commercial Bank');
  await expect(rows.last().getByRole('cell', { name: 'Date unavailable', exact: true })).toBeVisible();
});

test('the loan register refreshes and retries independently of the debt headline', async ({ page }) => {
  await page.clock.setFixedTime(new Date(Date.now() + 2 * 60 * 60 * 1000));
  let release!: () => void;
  const waitForRelease = new Promise<void>(resolve => { release = resolve; });
  let available = false;
  const requests = { overview: 0, timeline: 0 };
  page.on('request', request => {
    const path = new URL(request.url()).pathname;
    if (path === '/api/v1/debt/national') requests.overview += 1;
    if (path === '/api/v1/debt/timeline') requests.timeline += 1;
  });
  await page.route('**/api/v1/debt/loans', async route => {
    await waitForRelease;
    if (available) await route.fulfill({ json: { loans: [] } });
    else await route.fulfill({ status: 503, json: { status: 'unavailable' } });
  });
  await page.goto('/debt#loan-register');
  const register = page.getByRole('region', { name: 'The full loan register' });
  await expect(page.getByTestId('national-debt-outstanding')).toHaveText('KES 12.00T');
  // The loopback API prefetches an empty register. Retain that last response
  // during a failed background refetch, and retry without fetching the page again.
  await expect(register.getByText('No loan register records are available.')).toBeVisible();
  await expect(register.getByRole('alert')).toHaveCount(0);
  release();
  await expect(register.getByRole('alert')).toHaveText('The loan register could not be refreshed. Showing the last available result.');
  await expect(register.getByText('No loan register records are available.')).toBeVisible();
  const before = { ...requests };

  available = true;
  await register.getByRole('button', { name: 'Try again' }).click();
  await expect(register.getByText('No loan register records are available.')).toBeVisible();
  await expect(register.getByRole('alert')).toHaveCount(0);
  await expect(page.getByTestId('national-debt-outstanding')).toHaveText('KES 12.00T');
  expect(requests).toEqual(before);
});
