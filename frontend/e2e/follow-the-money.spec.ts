/** County Money flow, reporting periods, coverage and the separate national page. */
import { expect, test, type APIRequestContext } from '@playwright/test';
import type { CountyFiscalYears } from '../lib/utils';
import type { MoneyFlowData } from '../types';
import { countyTabs, waitForAppReady } from './utils/selectors';

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

test.describe('County detail — Money flow', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`/counties/${COUNTY_ID}`);
    await waitForAppReady(page);
    await countyTabs.followTheMoney(page).click();
    // Wait for the waterfall to render
    await expect(page.getByRole('button', { name: /^Allocated KES/ })).toBeVisible({ timeout: 15_000 });
  });

  test('shows allocated, spent and unspent on a common flow without a release or ring', async ({ page }) => {
    const panel = page.getByRole('tabpanel', { name: 'Money', exact: true });
    await expect(panel.getByRole('button', { name: /^Allocated KES/ })).toBeVisible();
    await expect(panel.getByRole('button', { name: /^Spent KES/ })).toBeVisible();
    await expect(panel.getByText(/Unspent KES/)).toBeVisible();
    await expect(panel.getByText(/Not yet paid out at report time/i)).toBeVisible();
    await expect(panel.getByText(/Funds Released|Efficiency/)).toHaveCount(0);
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
    await page.getByRole('button', { name: 'Source: ' + flow.source_document_title! }).click();
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
    const allocated = page.getByRole('button', { name: /^Allocated KES/ });
    const spent = page.getByRole('button', { name: /^Spent KES/ });
    const flagged = page.getByText(/^Recorded finding amounts for/);
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
    await expect(spent).toContainText('Unspent KES 8.00B');
    await expect(page.getByText(/spent 60% of its allocation/)).toBeVisible();

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
    await expect(page.getByText(`Counties · FY ${defaultYear}`, { exact: true })).toBeVisible();
  });

  test('selecting another period refreshes the national spending verdict and county cards', async ({
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
    const national = {
      ...makeFlow(null, 'All counties', 40e9, 28e9, 2e9, 70),
      source_document_url: 'https://cob.go.ke/reports/synthetic-county-implementation.pdf',
      source_document_title: 'Synthetic county budget implementation report',
    };
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
    const verdictHeading = page.locator('#money-flow-verdict');
    const spending = page.getByRole('region', { name: 'County spending' });
    await expect(picker).toHaveValue(defaultYear);
    await expect(page.getByText(`Counties · FY ${defaultYear}`, { exact: true })).toBeVisible();
    const initialVerdict = await verdictHeading.textContent();

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
    const verdict = page.getByRole('region', { name: /^Counties spent 70%/ });
    await expect(verdict.getByRole('heading')).toHaveText(
      'Counties spent 70% of their allocation (KES 28.00B of KES 40.00B).'
    );
    await expect(verdict.getByTestId('national-spending-flow')).toHaveCount(1);
    await expect(verdict.getByText('KES 12.00B not yet spent at the time of the report.')).toBeVisible();
    const source = verdict.getByText('Source and method');
    await source.focus();
    await page.keyboard.press('Enter');
    await expect(verdict.getByRole('link')).toHaveAttribute('href', national.source_document_url);
    await page.keyboard.press('Tab');
    await expect(verdict.getByRole('link')).toBeFocused();
    await expect(page.getByRole('region', { name: 'At a glance' })).toHaveCount(0);
    const audit = page.getByRole('region', { name: 'National audit finding amounts' });
    await expect(audit).toContainText('KES 2.00B');
    await expect(audit).toContainText('not proven loss or theft');
    await expect(spending).toContainText(`FY ${year}`);
    await expect(spending.getByText('National 70%', { exact: true })).toBeVisible();
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
    await expect(nairobi).toContainText('QuestionedKES 2.00B');
    await expect(kiambu).toContainText('QuestionedKES 0');
    await expect(
      nairobi.getByRole('img', { name: 'Nairobi: 60% of allocation spent. Target: 70%. National share spent: 70%.' })
    ).toBeVisible();

    // Returning to the cached initial period must update the visible selection
    // and restore its figures, rather than retaining the other period's data.
    await picker.selectOption(defaultYear);
    await expect(picker).toHaveValue(defaultYear);
    await expect(verdictHeading).toHaveText(initialVerdict!);
    await expect(spending).toContainText(`FY ${defaultYear}`);
  });

  test.describe('county distribution on a touch screen', () => {
    test.use({ hasTouch: true });

    test('explores 47 recorded shares and filters below-target counties alongside search', async ({
      page, request,
    }) => {
      await page.setViewportSize({ width: 360, height: 900 });
      const { years, defaultYear } = await reportedYears(request);
      const year = years.find((value) => value !== defaultYear)!;
      expect(year).toBeTruthy();
      const boundary = 69.96;
      const makeFlow = (id: number, label: string, percentage: number | null): MoneyFlowData => ({
        county_id: id, county_name: label, fiscal_year: year, budget_source: 'cob_cbirr',
        total_waste_estimate: null, efficiency_score: percentage,
        stages: [
          { stage: 'Allocated', label: 'Allocation', amount: 10e9 },
          { stage: 'Spent', label: 'Expenditure', amount: percentage == null ? null : percentage * 100e6 },
        ],
      });
      const counties = [
        makeFlow(1, 'Anchor', 0),
        ...Array.from({ length: 7 }, (_, index) => makeFlow(index + 2, `Boundary ${index + 1}`, boundary)),
        ...Array.from({ length: 39 }, (_, index) => makeFlow(index + 9, `County ${index + 9}`, 70 + index / 2)),
      ];
      const unavailable = makeFlow(48, 'Unreported', null);
      await page.route(
        (url) => url.pathname === '/api/v1/money-flow/all-counties' && url.searchParams.get('year') === year,
        (route) => route.fulfill({ json: counties })
      );
      await page.route(
        (url) => url.pathname === '/api/v1/audit/money-flow/national' && url.searchParams.get('year') === year,
        (route) => route.fulfill({ json: { ...unavailable, county_id: null, efficiency_score: 71 } })
      );
      await page.goto('/transparency');
      await waitForAppReady(page);
      const picker = page.getByRole('combobox', { name: 'Fiscal year & reporting period' });
      await picker.selectOption(year);
      const section = page.getByRole('region', { name: 'County spending' });
      const plot = section.getByRole('button', { name: 'Explore county spending shares' });
      const readout = section.locator('figure p[aria-live="polite"]');
      await expect(section.getByText('8 of 47 reporting counties spent less than the 70% target.')).toBeVisible();
      await expect(plot.locator('[data-below]')).toHaveCount(47);
      await expect(section.getByText('National 71%', { exact: true })).toHaveCount(0);
      const coincidentDot = plot.locator('[data-below=true]').nth(1);
      await coincidentDot.scrollIntoViewIfNeeded();
      const bounds = await coincidentDot.boundingBox();
      expect(bounds).toBeTruthy();
      for (const label of ['Boundary 1 · 69.96%', 'Boundary 7 · 69.96%']) {
        await page.touchscreen.tap(bounds!.x + bounds!.width / 2, bounds!.y + bounds!.height / 2);
        await expect(readout).toHaveText(label);
      }
      const search = section.getByRole('searchbox', { name: 'Find your county' });
      await search.tap();
      await expect(readout).toBeEmpty();
      await plot.focus();
      await page.keyboard.press('Home');
      await expect(readout).toHaveText('Anchor · 0%');
      await page.keyboard.press('ArrowRight');
      await expect(readout).toHaveText('Boundary 1 · 69.96%');
      await section.getByRole('button', { name: 'Next county' }).click();
      await expect(readout).toHaveText('Boundary 2 · 69.96%');
      const tableToggle = section.getByText('Read chart data');
      await tableToggle.focus();
      await page.keyboard.press('Enter');
      await expect(section.getByRole('row', { name: 'Boundary 7 69.96%' })).toBeVisible();
      await expect(section.getByRole('table').getByRole('row')).toHaveCount(48);
      await expect(readout).toHaveText('Boundary 2 · 69.96%');
      await page.keyboard.press('Escape');
      await expect(readout).toBeEmpty();
      await tableToggle.click();

      const chip = section.getByRole('button', { name: '8 below target' });
      const cards = section.getByRole('list', { name: /Counties ordered by/ });
      await chip.click();
      await expect(chip).toHaveAttribute('aria-pressed', 'true');
      await expect(cards.getByRole('listitem')).toHaveCount(8);
      await expect(cards.getByText('KES 10.00B allocated').first()).toBeVisible();
      await search.fill('County 9');
      await expect(section.getByText('No counties below the target match your search.')).toBeVisible();
      await chip.click();
      await expect(cards.getByRole('link', { name: 'County 9', exact: true })).toBeVisible();
      await search.fill('');
      await chip.click();
      await picker.selectOption(defaultYear);
      await expect(chip).toHaveCount(0);
      await picker.selectOption(year);
      await expect(chip).toHaveAttribute('aria-pressed', 'false');
    });
  });

  test('shows ten rich county cards and searches all 47 before expansion', async ({ page, request }) => {
    await page.setViewportSize({ width: 360, height: 800 });
    const { defaultYear, years } = await reportedYears(request);
    const year = years.find((availableYear) => availableYear !== defaultYear);
    expect(year, 'The county spending fixture requires a non-default period').toBeTruthy();
    const countyRows: MoneyFlowData[] = Array.from({ length: 47 }, (_, index) => {
      const allocated = 10e9;
      const share = 50 + index;
      const spent = allocated * share / 100;
      return {
        county_id: index + 1,
        county_name: `Test county ${String(index + 1).padStart(2, '0')}`,
        fiscal_year: year!,
        budget_source: 'cob_cbirr',
        efficiency_score: share,
        total_waste_estimate: null,
        stages: [
          { stage: 'Allocated', label: 'Allocation', amount: allocated },
          { stage: 'Spent', label: 'Expenditure', amount: spent, gap_from_prev: allocated - spent },
          { stage: 'Flagged', label: 'Questioned', amount: null },
        ],
      };
    });
    await page.route(
      (url) => url.pathname === '/api/v1/money-flow/all-counties' && url.searchParams.get('year') === year,
      (route) => route.fulfill({ json: countyRows }),
    );
    await page.goto('/transparency');
    await waitForAppReady(page);
    await page.getByRole('combobox', { name: 'Fiscal year & reporting period' }).selectOption(year!);

    const spending = page.getByRole('region', { name: 'County spending' });
    const list = spending.getByRole('list', { name: /Counties ordered by/ });
    const items = list.getByRole('listitem');
    await expect(items).toHaveCount(10);
    await expect(items.first()).toContainText('Well below target');
    await expect(items.first()).toContainText('KES 10.00B allocated');
    await expect(items.first()).toContainText('SpentKES 5.00B');
    await expect(items.first()).toContainText('GapKES 5.00B');
    await expect(items.first().getByLabel('Audit amount unavailable')).toHaveText('—');
    await expect(spending.getByText(/Audit amounts are unavailable for/)).toHaveCount(1);

    const search = spending.getByRole('searchbox', { name: 'Find your county' });
    await search.fill('Test county 47');
    await expect(items).toHaveCount(1);
    await expect(items.first()).toContainText(/^47Test county 47/);
    await expect(items.first()).toContainText('Above target');
    await spending.getByRole('button', { name: 'Clear county search' }).click();
    await expect(search).toBeFocused();
    await expect(items).toHaveCount(10);

    const showAll = spending.getByRole('button', { name: 'Show all 47 counties' });
    await showAll.focus();
    await page.keyboard.press('Enter');
    await expect(items).toHaveCount(47);
    await expect(list.getByRole('link', { name: 'Test county 11' })).toBeFocused();
    await spending.getByRole('button', { name: 'Show fewer' }).click();
    await expect(items).toHaveCount(10);
    await expect(showAll).toHaveAttribute('aria-expanded', 'false');
  });

});

test.describe('Follow the Money — efficiency + provenance', () => {
  test('the paid share is a plain-language statement', async ({ page }) => {
    await page.goto(`/counties/${COUNTY_ID}`);
    await waitForAppReady(page);
    await countyTabs.followTheMoney(page).click();
    await expect(page.getByText(/spent 60% of its allocation/)).toBeVisible();
    await expect(page.getByText(/Efficiency/)).toHaveCount(0);
  });

  test('committed-amount note is shown when present', async ({ page }) => {
    await page.goto(`/counties/${COUNTY_ID}`);
    await waitForAppReady(page);
    await countyTabs.followTheMoney(page).click();

    // Copy from FollowTheMoney.tsx — regression guard if the footer gets
    // refactored away by accident.
    await expect(
      page.getByText(/Reported procurement commitments KES/).first()
    ).toBeVisible({ timeout: 10_000 });
  });
});

// Pin the mounted data-read contract via the supported deep link. The active
// shell-click committed-note regression above separately covers lazy selection (#450).
test.describe('Follow the Money — read states', () => {
  for (const [lang, tabName, failedMessage, loadingMessage, emptyMessage, retryName] of [
    ['en', 'Money', 'Could not load money flow for this period.', 'Tracing the money...', 'No money flow data available for this period.', 'Try again'],
    ['sw', 'Fedha', 'Imeshindikana kupakia mtiririko wa pesa kwa kipindi hiki.', 'Inafuatilia pesa...', 'Hakuna data ya mtiririko wa pesa inayopatikana kwa kipindi hiki.', 'Jaribu tena'],
    ['plain', 'Money', 'We could not load money flow for this period.', 'Loading money flow...', 'No money flow data is available for this period.', 'Try again'],
  ] as const) {
    for (const width of [375, 1280]) {
      test(`${lang} at ${width}px distinguishes failed, pending and successful absence reads`, async ({ page, request }, testInfo) => {
        await page.setViewportSize({ width, height: 900 });
        await page.addInitScript(value => localStorage.setItem('auditgava-lang', value), lang);
        const { metadata } = await reportedYears(request);
        const errors: string[] = []; page.on('pageerror', error => errors.push(error.message));
        let calls = 0;
        let retrying = false;
        let observeRetry!: () => void;
        const retryObservation = new Promise<void>(resolve => { observeRetry = resolve; });
        let release!: () => void;
        const pending = new Promise<void>(resolve => { release = resolve; });
        await page.route(url => url.pathname === `/api/v1/counties/${COUNTY_ID}/money-flow`, async route => {
          // Force loading to precede observation of the retry request.
          if (retrying) await retryObservation;
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
        await expect(page.getByRole('tab', { name: tabName, exact: true })).toHaveAttribute('aria-selected', 'true');
        const panel = page.locator('[class*="moneyReport"]');
        await expect(panel.getByRole('alert')).toContainText(failedMessage);
        await expect(panel.getByText(emptyMessage, { exact: true })).toHaveCount(0);
        await expect(panel.locator('[data-money-stage]')).toHaveCount(0);
        expect(calls).toBe(1);
        const picker = panel.getByRole('combobox');
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
        expect(calls).toBe(1);
        observeRetry();
        await expect.poll(() => calls).toBe(2);
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
    await expect(countyTabs.followTheMoney(page)).toHaveAttribute('aria-selected', 'true');
    const panel = page.locator('[class*="moneyReport"]');
    await expect(panel.getByRole('status')).toContainText('Loading reporting periods...');
    expect(moneyCalls).toBe(0);
    await expect(panel.getByRole('combobox')).toHaveCount(0);
    release();
    await expect(panel.getByRole('alert')).toContainText('Could not load reporting periods.');
    expect(moneyCalls).toBe(0);
    await expect(panel.getByText('No money flow data available for this period.')).toHaveCount(0);
    await panel.getByRole('button', { name: 'Try again' }).click();
    await expect(panel.getByText(/Reported procurement commitments KES/).first()).toBeVisible();
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
    await expect(countyTabs.followTheMoney(page)).toHaveAttribute('aria-selected', 'true');
    const panel = page.locator('[class*="moneyReport"]');
    await expect(panel.getByRole('status')).toContainText('No reporting periods are available for money flow.');
    await expect(panel.getByRole('combobox')).toHaveCount(0);
    await expect(panel.getByRole('alert')).toHaveCount(0);
    await expect(panel.getByText('No money flow data available for this period.')).toHaveCount(0);
    expect(moneyCalls).toBe(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}
