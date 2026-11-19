import { expect, test } from '@playwright/test';
import { nav } from './utils/selectors';

test('audit reports page filters and search', async ({ page }) => {
  await page.goto('/audits');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Audit Findings');
  await expect(page.locator('table').last().locator('tbody tr')).toHaveCount(20);
  await expect(page.locator('table').last().locator('tbody')).toContainText('KES 1.0M');
  const severity = page.getByRole('combobox', { name: 'Severity', exact: true });
  const response = page.waitForResponse(r => new URL(r.url()).pathname === '/api/v1/audit/findings' && new URL(r.url()).searchParams.get('severity') === 'Critical');
  await severity.selectOption('Critical');
  expect((await response).ok()).toBe(true);
  await expect(page.getByText('No findings match your filters.', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Clear filters', exact: true }).click();
  await expect(page.locator('table').last().locator('tbody tr')).toHaveCount(20);
  await expect(page.locator('table').last().locator('tbody')).toContainText('KES 1.0M');
});

test('long audit section values fit narrow viewports and keep their accessible filter names', async ({ page }) => {
  const controlsSection = 'Report on Effectiveness of Internal Controls, Risk Management and Governance';
  const unmappedSection = 'A future report section for which the API has not supplied a short display name';
  // Simulate an expired SSR payload so the real hook reads the synthetic section options in the browser.
  await page.clock.setFixedTime(new Date(Date.now() + 2 * 60 * 60 * 1000));
  await page.route('**/api/v1/audit/summary', async (route) => {
    const response = await route.fetch();
    const summary = await response.json();
    await route.fulfill({
      response,
      json: {
        ...summary,
        findings_by_type: { [controlsSection]: 1, [unmappedSection]: 1 },
      },
    });
  });
  await page.setViewportSize({ width: 360, height: 780 });
  await page.goto('/audits');

  const section = page.getByRole('combobox', { name: 'Section', exact: true });
  await expect(section.locator('option')).toHaveText(['All sections', unmappedSection, 'Internal controls']);
  await expect(page.getByRole('combobox', { name: 'Year', exact: true })).toBeVisible();
  await expect(page.getByRole('combobox', { name: 'Audit opinion', exact: true })).toBeVisible();
  await expect(page.getByRole('combobox', { name: 'Severity', exact: true })).toBeVisible();
  await expect(page.getByRole('combobox', { name: 'Status', exact: true })).toBeVisible();

  const filtered = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname === '/api/v1/audit/findings' &&
      url.searchParams.get('query_type') === controlsSection;
  });
  await section.selectOption({ label: 'Internal controls' });
  expect((await filtered).ok()).toBe(true);
  await section.selectOption({ label: unmappedSection });

  const typeChart = page.getByRole('heading', { name: 'Findings by Type', exact: true }).locator('..');
  await typeChart.locator('.recharts-bar-rectangle').first().hover();
  await expect(typeChart.locator('.recharts-tooltip-label')).toHaveText(controlsSection);
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBe(360);

  for (const width of [320, 360, 390, 768, 1024, 1280, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
  }
  await page.setViewportSize({ width: 360, height: 780 });
  const menu = nav.mobileMenuToggle(page);
  await expect(menu).toBeInViewport({ ratio: 1 });
  await menu.click();
  await expect(page.getByRole('dialog', { name: /mobile navigation/i })).toBeVisible();
});

test('phone finding cards show the cited title or published text and keep the report page link', async ({ page }) => {
  const source = 'https://example.test/reports/audit.pdf#page=31';
  const title = 'Unsupported inventory adjustments';
  const paragraph = 'The inventory register did not explain the adjustments.';
  const fallback = 'The report describes a record without a separate heading.';
  const entry = {
    entity_id: 101, audited_entity_name: 'County Assembly of Nairobi', period_id: 21,
    audit_year: 2024, query_type: 'Report on Effectiveness of Internal Controls, Risk Management and Governance',
    severity: 'warning',
  };
  await page.clock.setFixedTime(new Date(Date.now() + 2 * 60 * 60 * 1000));
  await page.route('**/api/v1/audit/findings?**', (route) => route.fulfill({
    json: {
      page: 1, limit: 20, total: 2,
      items: [
        { ...entry, id: 701, finding_title: title, finding_text: paragraph, amount: 0, page_ref: 'p.31', source_document_url: source },
        { ...entry, id: 702, finding_title: null, finding_text: fallback, amount: null, source_document_url: null },
      ],
    },
  }));

  await page.setViewportSize({ width: 360, height: 780 });
  await page.goto('/audits');
  const cards = page.getByRole('list', { name: 'All findings', exact: true });
  const titled = cards.getByRole('listitem').filter({ has: page.getByRole('heading', { name: title, exact: true }) });
  await expect(titled.getByText('County Assembly of Nairobi')).toBeVisible();
  await expect(titled.getByText(/2024$/)).toBeVisible();
  await expect(titled.getByText('Warning', { exact: true })).toBeVisible();
  await expect(titled.getByText('Section: Internal controls', { exact: true })).toBeVisible();
  await expect(titled.getByText('Amount: KES 0', { exact: true })).toBeVisible();
  await expect(titled.getByText(paragraph, { exact: true })).toHaveCount(0);
  const link = titled.getByRole('link', { name: 'Source: report p.31' });
  await expect(link).toHaveAttribute('href', source);
  expect((await link.boundingBox())?.height).toBeGreaterThanOrEqual(44);
  const untitled = cards.getByRole('listitem').filter({ has: page.getByRole('heading', { name: fallback, exact: true }) });
  await expect(untitled.getByText('Amount: not stated', { exact: true })).toBeVisible();
  await expect(untitled.getByRole('link')).toHaveCount(0);

  await page.setViewportSize({ width: 767, height: 900 });
  await expect(cards).toBeVisible();
  await page.setViewportSize({ width: 768, height: 900 });
  await expect(cards).toHaveCount(0);
  const table = page.getByRole('table').filter({
    has: page.getByRole('columnheader', { name: 'Severity', exact: true }),
  });
  await expect(table.getByRole('row').nth(1)).toHaveAttribute('title', paragraph);
  await expect(table.getByRole('link', { name: 'View OAG source report, p.31' })).toHaveAttribute('href', source);
});

test('audit collection headline and annual bars preserve exact scoped counts with accessible readouts', async ({ page }) => {
  await page.clock.setFixedTime(new Date(Date.now() + 2 * 60 * 60 * 1000));
  await page.route('**/api/v1/audit/summary', async route => {
    const response = await route.fetch();
    await route.fulfill({ response, json: {
      ...await response.json(), total_findings: 60, withheld_findings: 2,
      year_range: { min_year: 2021, max_year: 2025 },
    } });
  });
  await page.route('**/api/v1/audit/trends', route => route.fulfill({ json: {
    years: [2021, 2022, 2023, 2024, 2025],
    findings_per_year: { '2021': 12, '2022': 0, '2023': 14, '2024': 8, '2025': 20 },
    amount_per_year: {}, opinion_per_year: null, opinion_per_year_reason: null,
  } }));
  await page.goto('/audits');
  const headline = page.locator('[data-audit-headline]');
  await expect(headline.getByText('60', { exact: true })).toBeVisible();
  await expect(headline.getByText('Questioned ≠ confirmed loss', { exact: true })).toBeVisible();
  const source = headline.getByRole('button', { name: 'Source: Auditor-General' });
  await source.press('Enter');
  const sheet = page.getByRole('dialog', { name: 'About these finding counts' });
  await expect(sheet).toBeVisible();
  await expect(sheet).toContainText('2 findings withheld');
  await expect(sheet.getByRole('link', { name: 'View data sources' })).toHaveAttribute('href', '/sources');
  await page.keyboard.press('Escape');
  await expect(sheet).toBeHidden();
  await expect(source).toBeFocused();

  const chart = page.locator('[data-audit-year-chart]');
  await expect(chart.getByText('54 published findings have a recorded audit year.')).toBeVisible();
  await expect(chart.getByRole('button')).toHaveCount(5);
  await expect(chart.getByRole('button', { name: '2022 · 0 Findings' })).toBeVisible();
  await expect(chart).toContainText('Reports read per year unavailable');
  const year = chart.getByRole('button', { name: '2024 · 8 Findings' });
  const readout = chart.locator('[aria-live]');
  await year.focus();
  await expect(readout).toHaveText('2024 · 8');
  await year.press('Enter');
  await expect(year).toHaveAttribute('aria-pressed', 'true');
  await year.press('Escape');
  await expect(year).toHaveAttribute('aria-pressed', 'false');
  await expect(readout).toBeEmpty();
  await year.hover();
  await expect(readout).toHaveText('2024 · 8');
  await year.click();
  await year.click();
  await expect(readout).toBeEmpty();
  await chart.getByText('Read chart data', { exact: true }).click();
  const table = chart.getByRole('table');
  await expect(table.getByRole('row')).toHaveCount(6);
  await expect(table.getByRole('row', { name: '2022 0' })).toBeVisible();
});

test('audit year bars show unavailable counts and preserve measured zero', async ({ page }) => {
  await page.clock.setFixedTime(new Date(Date.now() + 2 * 60 * 60 * 1000));
  await page.route('**/api/v1/audit/trends', route => route.fulfill({ json: {
    years: [2021, 2022, 2023], findings_per_year: { '2021': 0, '2023': -3 },
    amount_per_year: {}, opinion_per_year: null, opinion_per_year_reason: null,
  } }));
  await page.goto('/audits');
  const chart = page.locator('[data-audit-year-chart]');
  await expect(chart.getByRole('button', { name: '2021 · 0 Findings' })).toBeVisible();
  await expect(chart.getByRole('button', { name: '2022 · Unavailable Findings' })).toBeVisible();
  await expect(chart.getByRole('button', { name: '2023 · Unavailable Findings' })).toBeVisible();
  await expect(chart.getByText('Published findings with a recorded audit year', { exact: true })).toBeVisible();
  await expect(chart.locator('button span[aria-hidden]')).toHaveCount(0);
});

test('audit year bars support touch, clear elsewhere and fit the real phone width', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 360, height: 800 }, hasTouch: true, reducedMotion: 'reduce' });
  try {
    const page = await context.newPage();
    await page.goto('/audits');
    const source = page.locator('[data-audit-headline]').getByRole('button', { name: 'Source: Auditor-General' });
    await source.tap();
    await expect(page.getByRole('dialog', { name: 'About these finding counts' })).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(source).toBeFocused();
    const chart = page.locator('[data-audit-year-chart]');
    const bar = chart.getByRole('button').first();
    expect((await bar.boundingBox())!.width).toBeGreaterThanOrEqual(44);
    await bar.tap();
    await expect(bar).toHaveAttribute('aria-pressed', 'true');
    await bar.tap();
    await expect(bar).toHaveAttribute('aria-pressed', 'false');
    await expect(chart.locator('[aria-live]')).toBeEmpty();
    await bar.tap();
    await page.getByRole('heading', { name: 'Findings by audit year', exact: true }).tap();
    await expect(bar).toHaveAttribute('aria-pressed', 'false');
    await expect(chart.locator('[aria-live]')).toBeEmpty();
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBe(360);
  } finally {
    await context.close();
  }
});

test('audit source details distinguish a missing withheld count from a true zero', async ({ page }) => {
  await page.clock.setFixedTime(new Date(Date.now() + 2 * 60 * 60 * 1000));
  let zero = false;
  await page.route('**/api/v1/audit/summary', async route => {
    const response = await route.fetch();
    const summary = await response.json();
    delete summary.withheld_findings;
    await route.fulfill({ response, json: { ...summary, total_findings: 0, ...(zero ? { withheld_findings: 0 } : {}) } });
  });
  await page.goto('/audits');
  const headline = page.locator('[data-audit-headline]');
  await expect(headline.getByText('0', { exact: true })).toBeVisible();
  await headline.getByRole('button', { name: 'Source: Auditor-General' }).click();
  const sheet = page.getByRole('dialog', { name: 'About these finding counts' });
  await expect(sheet.getByText('The number of withheld findings is unavailable.')).toBeVisible();
  zero = true;
  await page.reload();
  await headline.getByRole('button', { name: 'Source: Auditor-General' }).click();
  await expect(sheet).toContainText('0 findings withheld by the publication checks.');
});

test('a failed annual query can be retried and an empty series stays explicit', async ({ page }) => {
  await page.clock.setFixedTime(new Date(Date.now() + 2 * 60 * 60 * 1000));
  let failing = true;
  await page.route('**/api/v1/audit/trends', route => failing
    ? route.fulfill({ status: 503, json: { detail: 'Synthetic temporary error' } })
    : route.fulfill({ json: { years: [], findings_per_year: {}, amount_per_year: {},
      opinion_per_year: null, opinion_per_year_reason: null } }));
  await page.goto('/audits');
  const section = page.getByRole('heading', { name: 'Findings by audit year', exact: true }).locator('..');
  await expect(section.getByRole('alert')).toHaveText('Findings by audit year could not be loaded.', { timeout: 20_000 });
  failing = false;
  await section.getByRole('button', { name: 'Try again' }).click();
  await expect(section.getByText('No published findings with a recorded audit year are available.')).toBeVisible();
  await expect(section.locator('[data-audit-year-chart]')).toHaveCount(0);
});

test('a longer audit year series stays inside its keyboard-scrollable region', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await page.clock.setFixedTime(new Date(Date.now() + 2 * 60 * 60 * 1000));
  const years = Array.from({ length: 20 }, (_, index) => 2001 + index);
  await page.route('**/api/v1/audit/trends', route => route.fulfill({ json: {
    years, findings_per_year: Object.fromEntries(years.map((year, index) => [year, index])),
    amount_per_year: {}, opinion_per_year: null, opinion_per_year_reason: null,
  } }));
  await page.goto('/audits');
  const region = page.getByRole('region', { name: 'Audit year bars' });
  await expect(region.getByRole('button')).toHaveCount(20);
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBe(360);
  expect(await region.evaluate(element => element.scrollWidth)).toBeGreaterThan(await region.evaluate(element => element.clientWidth));
  await region.focus();
  await expect(region).toBeFocused();
  for (let step = 0; step < 8; step++) await page.keyboard.press('ArrowRight');
  await expect.poll(() => region.evaluate(element => element.scrollLeft)).toBeGreaterThan(0);
  await page.locator('[data-audit-year-chart]').getByText('Read chart data', { exact: true }).click();
  await expect(page.locator('[data-audit-year-chart]').getByRole('row')).toHaveCount(21);
});
