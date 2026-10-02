/**
 * Follow the Money — waterfall on the county detail page.
 *
 * Primary regression guards:
 *   - The "Funds Released" stage (labelled as a proxy via
 *     `committed_amount`) must stay OUT of the waterfall — it was
 *     dropped in v1.1.1 because it produced impossible numbers
 *     (spent > released).
 *   - The waterfall must be exactly 3 stages: Allocated / Spent /
 *     Flagged.
 *   - The "Unspent Funds" gap pill must carry the clarifier sub-label
 *     "Not missing" so readers can't confuse it with missing money.
 *   - The CoB source-document title must be a clickable link.
 *   - The FY selector must NOT show "FY FY…" (double prefix regression).
 *   - The default FY follows the API-reported period, rather than a
 *     wall-clock guess that could select a year with no data.
 */
import { expect, test, type APIRequestContext } from '@playwright/test';
import type { CountyFiscalYears } from '../lib/utils';
import type { MoneyFlowData } from '../types';
import { countyTabs, waterfall, waitForAppReady } from './utils/selectors';

const COUNTY_ID = '001'; // Nairobi — has data across FYs

const bareYear = (year: string) => year.replace(/^FY\s*/i, '').trim();

async function reportedYears(request: APIRequestContext) {
  // Use the same backend through Next's API proxy. The initial render is
  // prefetched server-side, so a browser route fixture cannot replace it.
  // The expected default comes from the API, never from the wall clock.
  const response = await request.get('/api/v1/counties/fiscal-years');
  expect(response.ok()).toBe(true);
  const metadata: CountyFiscalYears = await response.json();
  expect(metadata.default).toBeTruthy();
  const years = metadata.years.map((year) => bareYear(year.label));
  const defaultYear = bareYear(metadata.default!);
  expect(years).toContain(defaultYear);
  return { years, defaultYear, metadata };
}

test.describe('Follow the Money — waterfall shape', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`/counties/${COUNTY_ID}`);
    await waitForAppReady(page);
    await countyTabs.followTheMoney(page).click();
    // Wait for the waterfall to render
    await expect(waterfall.stage(page, 'Allocated')).toBeVisible({ timeout: 15_000 });
  });

  test('renders exactly three stages: Allocated / Spent / Flagged', async ({ page }) => {
    await expect(waterfall.stage(page, 'Allocated')).toBeVisible();
    await expect(waterfall.stage(page, 'Spent')).toBeVisible();
    await expect(waterfall.stage(page, 'Flagged')).toBeVisible();

    // The misleading 'Released' stage must be absent
    const releasedStage = page
      .locator('[class*="rounded"]')
      .filter({ hasText: /^RELEASED|Funds Released/i });
    await expect(releasedStage).toHaveCount(0);
  });

  test('Unspent Funds gap carries the "Not missing" clarifier', async ({ page }) => {
    await expect(page.getByText(/Unspent Funds/i).first()).toBeVisible();
    await expect(
      page.getByText(/Not missing|not yet paid out at report time/i).first()
    ).toBeVisible();
  });

  test('CoB source document is a clickable link with HTTPS URL', async ({ page, request }) => {
    const year = await page.getByRole('combobox', { name: 'Fiscal year', exact: true }).inputValue();
    const response = await request.get(`/api/v1/counties/${COUNTY_ID}/money-flow`, {
      params: { year },
    });
    expect(response.ok()).toBe(true);
    const flow: MoneyFlowData = await response.json();
    expect(flow.source_document_title).toBeTruthy();
    expect(flow.source_document_url).toBeTruthy();
    const source = page.getByRole('link', { name: flow.source_document_title!, exact: true });
    await expect(source).toBeVisible({ timeout: 10_000 });
    const href = await source.getAttribute('href');
    expect(href).toBe(flow.source_document_url);
    expect(href).toBe('https://example.invalid/auditgava-local-budget.pdf');
    // Make sure it opens in a new tab (external link convention)
    await expect(source).toHaveAttribute('target', '_blank');
    await expect(source).toHaveAttribute('rel', /noopener/);
  });
});

test.describe('Follow the Money — year selector', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`/counties/${COUNTY_ID}`);
    await waitForAppReady(page);
    await countyTabs.followTheMoney(page).click();
  });

  test('default year follows the API-reported period', async ({ page, request }) => {
    const { metadata } = await reportedYears(request);
    const select = page.getByRole('combobox', { name: 'Fiscal year', exact: true });
    await expect(select).toBeVisible();
    await expect(select).toHaveValue(metadata.default!);
    await expect(select.locator('option:checked')).toContainText(
      `FY ${bareYear(metadata.default!)}`
    );
    expect(
      await select
        .locator('option')
        .evaluateAll((options) => options.map((option) => (option as HTMLOptionElement).value))
    ).toEqual(metadata.years.map((year) => year.label));
  });

  test('dropdown labels never double-prefix "FY FY…"', async ({ page }) => {
    const select = page.getByRole('combobox', { name: 'Fiscal year', exact: true });
    await expect(select).toBeVisible();
    const optionTexts = await select.locator('option').allInnerTexts();
    expect(optionTexts.length).toBeGreaterThan(0);
    for (const text of optionTexts) {
      expect(text).not.toMatch(/FY\s*FY/);
    }
  });

  test('switching fiscal year changes the requested period and waterfall figures', async ({
    page,
    request,
  }) => {
    const { metadata } = await reportedYears(request);
    const select = page.getByRole('combobox', { name: 'Fiscal year', exact: true });
    await expect(select).toHaveValue(metadata.default!);
    const targetYear = [...metadata.years]
      .reverse()
      .find((year) => year.label !== metadata.default)?.label;
    expect(targetYear, 'The year-switch contract requires two reported periods').toBeTruthy();
    const year = targetYear!;
    // Fixtures are deliberately synthetic and only served inside this browser
    // test. Exact amounts prove the API result reached each rendered stage.
    const flow: MoneyFlowData = {
      county_id: 1,
      county_name: 'Nairobi County',
      fiscal_year: year,
      budget_source: 'cob_cbirr',
      total_waste_estimate: 1e9,
      efficiency_score: 60,
      stages: [
        { stage: 'Allocated', label: 'Budget Allocation', amount: 20e9 },
        {
          stage: 'Spent',
          label: 'Actual Expenditure',
          amount: 12e9,
          gap_from_prev: 8e9,
          gap_label: 'Unspent Funds',
        },
        {
          stage: 'Flagged',
          label: 'Auditor Flagged',
          amount: 1e9,
          gap_from_prev: 1e9,
          gap_label: 'Irregular/Unsupported Expenditure',
        },
      ],
    };
    const path = `/api/v1/counties/${COUNTY_ID}/money-flow`;
    await page.route(
      (url) => url.pathname === path && url.searchParams.get('year') === year,
      (route) => route.fulfill({ json: flow })
    );
    const allocated = page.getByText('Budget Allocation', { exact: true }).locator('..');
    const spent = page.getByText('Actual Expenditure', { exact: true }).locator('..');
    const flagged = page.getByText('Auditor Flagged', { exact: true }).locator('..');
    await expect(allocated).toContainText('KES');
    const initialAllocation = await allocated.textContent();
    const responsePromise = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return url.pathname === path && url.searchParams.get('year') === year;
    });
    await select.selectOption(year);
    expect((await responsePromise).ok()).toBe(true);
    await expect(select).toHaveValue(year);
    await expect(select.locator('option:checked')).toContainText(`FY ${bareYear(year)}`);
    await expect(allocated).toContainText('KES 20.00B');
    await expect(spent).toContainText('KES 12.00B');
    await expect(flagged).toContainText('KES 1.00B');
    await expect(page.getByText('Unspent Funds', { exact: true }).locator('..')).toContainText(
      'KES 8.00B'
    );
    await expect(page.getByText('60%', { exact: true })).toBeVisible();
    await expect(page.getByText('Fair Efficiency', { exact: true })).toBeVisible();

    await select.selectOption(metadata.default!);
    await expect(select).toHaveValue(metadata.default!);
    await expect(allocated).toHaveText(initialAllocation!);
  });
});

test.describe('Follow the Money — national page (/transparency)', () => {
  test('native selector shows the API-reported default and available periods', async ({
    page,
    request,
  }) => {
    const { years, defaultYear } = await reportedYears(request);
    await page.goto('/transparency');
    await waitForAppReady(page);

    const picker = page.getByRole('combobox', { name: 'Fiscal year & reporting period' });
    await expect(picker).toBeVisible();
    await expect(picker).toHaveValue(defaultYear);
    await expect(picker).toHaveAccessibleDescription(
      'Choose the reporting period for all figures below.'
    );
    expect(
      await picker
        .locator('option')
        .evaluateAll((options) => options.map((option) => (option as HTMLOptionElement).value))
    ).toEqual(years);
    await expect(picker.locator('option:checked')).toHaveCount(1);
    await expect(picker.locator('option:checked')).toContainText(`FY ${defaultYear}`);
    for (const label of await picker.locator('option').allTextContents()) {
      expect(label).not.toMatch(/FY\s*FY/);
    }
    await expect(page.getByRole('region', { name: 'At a glance' })).toContainText(
      `FY ${defaultYear}`
    );
  });

  test('selecting another period refreshes both national figures and county spending', async ({
    page,
    request,
  }) => {
    const { years, defaultYear } = await reportedYears(request);
    // A non-default period is not part of the SSR-prefetched cache. Route its
    // responses to synthetic figures so a stale summary/list cannot pass just
    // because two real reporting periods happen to publish the same amounts.
    const targetYear = [...years].reverse().find((year) => year !== defaultYear);
    expect(targetYear, 'The year-switch contract requires two reported periods').toBeTruthy();
    const year = targetYear!;
    const makeFlow = (
      id: number | null,
      name: string,
      allocated: number,
      spent: number,
      flagged: number,
      efficiency: number
    ): MoneyFlowData => ({
      county_id: id,
      county_name: name,
      fiscal_year: year,
      budget_source: 'cob_cbirr',
      total_waste_estimate: flagged,
      efficiency_score: efficiency,
      stages: [
        { stage: 'Allocated', label: 'Allocation', amount: allocated },
        { stage: 'Spent', label: 'Expenditure', amount: spent, gap_from_prev: allocated - spent },
        { stage: 'Flagged', label: 'Questioned', amount: flagged },
      ],
    });
    const national = makeFlow(null, 'All counties', 40e9, 28e9, 2e9, 70);
    const counties = [
      makeFlow(1, 'Nairobi County', 20e9, 12e9, 2e9, 60),
      makeFlow(2, 'Kiambu County', 20e9, 16e9, 0, 80),
    ];
    const nationalPath = '/api/v1/audit/money-flow/national';
    const countiesPath = '/api/v1/money-flow/all-counties';
    for (const [path, payload] of [
      [nationalPath, national],
      [countiesPath, counties],
    ] as const) {
      await page.route(
        (url) => url.pathname === path && url.searchParams.get('year') === year,
        (route) => route.fulfill({ json: payload })
      );
    }

    await page.goto('/transparency');
    await waitForAppReady(page);
    const picker = page.getByRole('combobox', { name: 'Fiscal year & reporting period' });
    const summary = page.getByRole('region', { name: 'At a glance' });
    const spending = page.getByRole('region', { name: 'County spending' });
    await expect(picker).toHaveValue(defaultYear);
    await expect(summary).toContainText(`FY ${defaultYear}`);
    const initialSummary = await summary.textContent();

    const responses = Promise.all(
      [nationalPath, countiesPath].map((path) =>
        page.waitForResponse((response) => {
          const url = new URL(response.url());
          return url.pathname === path && url.searchParams.get('year') === year;
        })
      )
    );
    await picker.selectOption(year);
    for (const response of await responses) expect(response.ok()).toBe(true);

    await expect(picker).toHaveValue(year);
    await expect(picker.locator('option:checked')).toContainText(`FY ${year}`);
    await expect(
      page.getByRole('heading', { name: 'KES 40.0B allocated, KES 28.0B reached programmes' })
    ).toBeVisible();
    await expect(summary).toContainText(`FY ${year}`);
    await expect(summary).toContainText('KES 40.00B');
    await expect(summary).toContainText('KES 12.00B');
    await expect(summary).toContainText('KES 2.00B');
    await expect(summary).toContainText('70%');
    await expect(spending).toContainText(`FY ${year}`);
    await expect(spending.getByRole('listitem')).toHaveCount(2);
    const nairobi = spending
      .getByRole('listitem')
      .filter({ has: page.getByRole('link', { name: 'Nairobi', exact: true }) });
    const kiambu = spending
      .getByRole('listitem')
      .filter({ has: page.getByRole('link', { name: 'Kiambu', exact: true }) });
    await expect(nairobi).toContainText('KES 20.00B');
    await expect(nairobi).toContainText('KES 12.00B');
    await expect(nairobi).toContainText('KES 8.00B');
    await expect(nairobi).toContainText('FlaggedKES 2.00B');
    await expect(kiambu).toContainText('FlaggedKES 0');
    await expect(
      nairobi.getByRole('img', { name: 'Nairobi: 60% budget execution. National reference: 70%' })
    ).toBeVisible();

    // Returning to the cached initial period must update the visible selection
    // and restore its figures, rather than retaining the other period's data.
    await picker.selectOption(defaultYear);
    await expect(picker).toHaveValue(defaultYear);
    await expect(summary).toHaveText(initialSummary!);
    await expect(spending).toContainText(`FY ${defaultYear}`);
  });
});

test.describe('Follow the Money — efficiency + provenance', () => {
  test('efficiency score is rendered as a percentage ring', async ({ page }) => {
    await page.goto(`/counties/${COUNTY_ID}`);
    await waitForAppReady(page);
    await countyTabs.followTheMoney(page).click();

    await expect(page.getByText('60%', { exact: true })).toBeVisible();
    await expect(
      page.getByText(/Good Efficiency|Fair Efficiency|Low Efficiency/i).first()
    ).toBeVisible();
  });

  test('committed-amount note is shown when present', async ({ page }) => {
    await page.goto(`/counties/${COUNTY_ID}`);
    await waitForAppReady(page);
    await countyTabs.followTheMoney(page).click();

    // Copy from FollowTheMoney.tsx — regression guard if the footer gets
    // refactored away by accident.
    await expect(
      page.getByText(/procurement-encumbered|earmarked for contracts/i)
    ).toBeVisible({ timeout: 10_000 });
  });
});

// Pin the mounted data-read contract via the supported deep link. The active
// shell-click committed-note regression above separately covers lazy selection (#450).
test.describe('Follow the Money — read states', () => {
  for (const [lang, tabName, failedMessage, loadingMessage, emptyMessage, retryName] of [
    ['en', 'Follow the Money', 'Could not load money flow for this period.', 'Tracing the money...', 'No money flow data available for this period.', 'Try again'],
    ['sw', 'Fuatilia Pesa', 'Imeshindikana kupakia mtiririko wa pesa kwa kipindi hiki.', 'Inafuatilia pesa...', 'Hakuna data ya mtiririko wa pesa inayopatikana kwa kipindi hiki.', 'Jaribu tena'],
    ['plain', 'Follow the Money', 'We could not load money flow for this period.', 'Loading money flow...', 'No money flow data is available for this period.', 'Try again'],
  ] as const) {
    for (const width of [375, 1280]) {
      test(`${lang} at ${width}px distinguishes failed, pending and successful absence reads`, async ({ page, request }, testInfo) => {
        await page.setViewportSize({ width, height: 900 });
        await page.addInitScript(value => localStorage.setItem('auditgava-lang', value), lang);
        const { metadata } = await reportedYears(request);
        const errors: string[] = []; page.on('pageerror', error => errors.push(error.message));
        let calls = 0;
        let retrying = false;
        let release!: () => void;
        const pending = new Promise<void>(resolve => { release = resolve; });
        await page.route(url => url.pathname === `/api/v1/counties/${COUNTY_ID}/money-flow`, async route => {
          calls++;
          if (!retrying) return route.fulfill({ status: 500, json: { detail: 'Synthetic failed read' } });
          // A gated successful empty response is different from a failed read.
          await pending;
          const response = await route.fetch();
          const flow: MoneyFlowData = await response.json();
          await route.fulfill({ response, json: { ...flow, stages: [] } });
        });
        await page.goto(`/counties/${COUNTY_ID}?tab=money`);
        await waitForAppReady(page);
        await expect(page.getByRole('button', { name: tabName, exact: true })).toHaveAttribute('aria-pressed', 'true');
        const panel = page.locator('[class*="moneyReport"]');
        await expect(panel.getByRole('alert')).toContainText(failedMessage);
        await expect(panel.getByText(emptyMessage, { exact: true })).toHaveCount(0);
        await expect(panel.locator('[data-money-stage]')).toHaveCount(0);
        expect(calls).toBe(1);
        const picker = panel.getByRole('combobox', { name: 'Fiscal year', exact: true });
        await expect(picker).toHaveValue(metadata.default!);
        const retry = panel.getByRole('button', { name: retryName, exact: true });
        await retry.focus();
        await expect(retry).toBeFocused();
        const box = await retry.boundingBox();
        expect(box!.height).toBeGreaterThanOrEqual(44);
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await testInfo.attach('money-flow-error', { body: await panel.screenshot(), contentType: 'image/png' });
        retrying = true;
        await retry.press('Enter');
        await expect(panel.getByRole('status')).toContainText(loadingMessage);
        await expect(panel.getByRole('button', { name: retryName, exact: true })).toHaveCount(0);
        expect(calls).toBe(2);
        release();
        await expect(panel.getByRole('status')).toContainText(emptyMessage);
        await expect(panel.getByRole('alert')).toHaveCount(0);
        await expect(panel.locator('[data-money-stage]')).toHaveCount(0);
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await testInfo.attach('money-flow-empty', { body: await panel.screenshot(), contentType: 'image/png' });
        expect(errors).toEqual([]);
      });
    }
  }
});

for (const width of [375, 1280]) {
  test(`Follow the Money at ${width}px waits for discovery and recovers failed reporting periods`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    let release!: () => void;
    const pending = new Promise<void>(resolve => { release = resolve; });
    let yearsCalls = 0;
    let moneyCalls = 0;
    page.on('request', req => { if (new URL(req.url()).pathname === `/api/v1/counties/${COUNTY_ID}/money-flow`) moneyCalls++; });
    await page.route(url => url.pathname === '/api/v1/counties/fiscal-years', async route => {
      yearsCalls++;
      if (yearsCalls === 1) {
        await pending;
        await route.fulfill({ status: 500, json: { detail: 'Synthetic discovery failure' } });
      } else await route.continue();
    });
    await page.goto(`/counties/${COUNTY_ID}?tab=money`);
    await waitForAppReady(page);
    await expect(countyTabs.followTheMoney(page)).toHaveAttribute('aria-pressed', 'true');
    const panel = page.locator('[class*="moneyReport"]');
    await expect(panel.getByRole('status')).toContainText('Loading reporting periods...');
    expect(moneyCalls).toBe(0);
    await expect(panel.getByRole('combobox')).toHaveCount(0);
    release();
    await expect(panel.getByRole('alert')).toContainText('Could not load reporting periods.');
    expect(moneyCalls).toBe(0);
    await expect(panel.getByText('No money flow data available for this period.')).toHaveCount(0);
    await panel.getByRole('button', { name: 'Try again' }).click();
    await expect(panel.getByText(/procurement-encumbered/)).toBeVisible();
    await expect(panel.getByRole('combobox')).toHaveValue('FY2025/26 9M');
    expect(yearsCalls).toBe(2);
    expect(moneyCalls).toBe(1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });

  test(`Follow the Money at ${width}px explains unavailable reporting periods without a money read`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    let moneyCalls = 0;
    page.on('request', req => { if (new URL(req.url()).pathname === `/api/v1/counties/${COUNTY_ID}/money-flow`) moneyCalls++; });
    await page.route(url => url.pathname === '/api/v1/counties/fiscal-years', route => route.fulfill({ json: { default: null, years: [] } }));
    await page.goto(`/counties/${COUNTY_ID}?tab=money`);
    await waitForAppReady(page);
    await expect(countyTabs.followTheMoney(page)).toHaveAttribute('aria-pressed', 'true');
    const panel = page.locator('[class*="moneyReport"]');
    await expect(panel.getByRole('status')).toContainText('No reporting periods are available for money flow.');
    await expect(panel.getByRole('combobox')).toHaveCount(0);
    await expect(panel.getByRole('alert')).toHaveCount(0);
    await expect(panel.getByText('No money flow data available for this period.')).toHaveCount(0);
    expect(moneyCalls).toBe(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}
