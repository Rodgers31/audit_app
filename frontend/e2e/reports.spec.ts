import { expect, test } from '@playwright/test';
import { nav } from './utils/selectors';

test('audit reports page filters and search', async ({ page }) => {
  await page.goto('/audits');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Audit Findings');
  const table = page.getByRole('table', { name: 'All findings' });
  await expect(table.locator('tbody tr')).toHaveCount(20);
  await table.locator('tbody').getByRole('button').first().click();
  await expect(page.locator('[data-audit-finding-pane]')).toContainText('KES 1,000,000');
  const severity = page.getByRole('combobox', { name: 'Severity', exact: true });
  const matches = page.waitForResponse(r => new URL(r.url()).pathname === '/api/v1/audit/findings' && new URL(r.url()).searchParams.get('severity') === 'WARNING');
  await severity.selectOption({ label: 'Warning' });
  const response = await matches;
  expect(response.ok()).toBe(true);
  const warningFindings = await response.json();
  expect(warningFindings.total).toBeGreaterThan(20);
  expect(warningFindings.items.every((finding: { severity: string }) => finding.severity === 'warning')).toBe(true);
  await expect(table.locator('tbody tr')).toHaveCount(20);
  await expect(page.locator('[data-audit-finding-pane]')).toHaveCount(0);
  await severity.selectOption({ label: 'Critical' });
  await expect(page.getByText('No findings match your filters.', { exact: true })).toBeVisible();
  await expect(page.locator('[data-audit-finding-pane]')).toHaveCount(0);
  await page.getByRole('button', { name: 'Clear filters', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'All findings', exact: true })).toBeFocused();
  await expect(table.locator('tbody tr')).toHaveCount(20);
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
  const targets = await page.getByRole('region', { name: 'All findings', exact: true })
    .getByRole('combobox').evaluateAll(controls => controls.map(control => control.getBoundingClientRect().height));
  expect(Math.min(...targets)).toBeGreaterThanOrEqual(44);

  const filtered = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname === '/api/v1/audit/findings' &&
      url.searchParams.get('query_type') === controlsSection;
  });
  await section.selectOption({ label: 'Internal controls' });
  expect((await filtered).ok()).toBe(true);
  await section.selectOption({ label: unmappedSection });

  await expect(page.getByRole('heading', { name: 'Findings by Type', exact: true })).toHaveCount(0);
  await expect(page.getByRole('region', { name: 'Findings by severity' })).toBeVisible();
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

  await page.setViewportSize({ width: 1023, height: 900 });
  await expect(cards).toBeVisible();
  await page.setViewportSize({ width: 1024, height: 900 });
  await expect(cards).toHaveCount(0);
  const table = page.getByRole('table', { name: 'All findings' });
  const open = table.getByRole('button', { name: title });
  const report = table.getByRole('link', { name: 'Source report · p.31' });
  await expect(report).toHaveAttribute('href', source);
  await page.context().route('https://example.test/reports/audit.pdf', route =>
    route.fulfill({ contentType: 'text/html', body: '<title>Synthetic source report</title>' }));
  const reportOpened = page.waitForEvent('popup');
  await report.click();
  const sourceTab = await reportOpened;
  await expect(sourceTab).toHaveURL(source);
  await sourceTab.close();
  await expect(page.locator('[data-audit-finding-pane]')).toHaveCount(0);
  await open.focus();
  await open.press('Enter');
  const pane = page.getByRole('complementary', { name: title });
  await expect(pane.getByRole('heading', { name: title })).toBeFocused();
  await expect(pane.getByText(paragraph)).toBeVisible();
  await expect(pane.getByText('KES 0', { exact: true })).toBeVisible();
  await expect(pane.getByRole('link', { name: 'Source report · p.31' })).toHaveAttribute('href', source);
  await page.keyboard.press('Escape');
  await expect(pane).toHaveCount(0);
  await expect(open).toBeFocused();

  // Clicking a noninteractive cell opens the same pane.
  const sparse = table.getByRole('row').filter({ hasText: fallback });
  await sparse.getByRole('cell', { name: '2024', exact: true }).click();
  const sparsePane = page.getByRole('complementary', { name: 'Finding details' });
  await expect(sparsePane.getByText(fallback)).toBeVisible();
  await expect(sparsePane.getByText('Amount mentioned').locator('+ dd')).toHaveText('Not stated');
  await expect(sparsePane.getByText('Source report unavailable')).toBeVisible();
  await expect(sparsePane.getByRole('link')).toHaveCount(0);
  await sparsePane.getByRole('button', { name: 'Close finding details' }).click();
  await expect(sparse.getByRole('button')).toBeFocused();
});

test('desktop sorting stays on the current server page and paging closes the pane', async ({ page }) => {
  const later = { id: 401, finding_title: 'Zebra example', finding_text: 'Later finding.', audit_year: 2024, severity: 'warning' };
  const earlier = { id: 402, finding_title: 'Aardvark example', finding_text: 'Earlier finding.', audit_year: 2023, severity: 'critical' };
  const unknownYear = { id: 403, finding_title: 'Missing year example', finding_text: 'No year recorded.', audit_year: null, severity: 'info' };
  await page.clock.setFixedTime(new Date(Date.now() + 2 * 60 * 60 * 1000));
  const requestedPages: string[] = [];
  await page.route('**/api/v1/audit/findings?**', route => {
    const responsePage = new URL(route.request().url()).searchParams.get('page') ?? '1';
    requestedPages.push(responsePage);
    return route.fulfill({ json: {
      total: 21, page: Number(responsePage), limit: 20,
      items: responsePage === '1' ? [later, earlier, unknownYear] : [{ ...later, id: 404, finding_title: 'Second page finding' }],
    } });
  });
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto('/audits');
  const table = page.getByRole('table', { name: 'All findings' });
  const rowTitles = table.locator('tbody').getByRole('button');
  await expect(rowTitles).toHaveText([later.finding_title, earlier.finding_title, unknownYear.finding_title]);
  await expect(table.locator('[aria-sort]')).toHaveCount(0);
  const year = table.getByRole('button', { name: 'Sort Year on this page' });
  await year.press('Enter');
  await expect(year.locator('..')).toHaveAttribute('aria-sort', 'ascending');
  await expect(rowTitles).toHaveText([earlier.finding_title, later.finding_title, unknownYear.finding_title]);
  await year.press('Enter');
  await expect(year.locator('..')).toHaveAttribute('aria-sort', 'descending');
  await expect(rowTitles).toHaveText([later.finding_title, earlier.finding_title, unknownYear.finding_title]);
  await table.getByRole('button', { name: 'Sort Finding on this page' }).click();
  await expect(rowTitles).toHaveText([earlier.finding_title, unknownYear.finding_title, later.finding_title]);
  expect(requestedPages).toEqual(['1']);
  await table.getByRole('button', { name: earlier.finding_title }).click();
  const pane = page.getByRole('complementary', { name: earlier.finding_title });
  await expect(pane).toBeVisible();
  const findings = page.getByRole('region', { name: 'All findings', exact: true });
  await findings.getByRole('button', { name: 'Next', exact: true }).click();
  await expect(findings.getByRole('heading', { name: 'All findings' })).toBeFocused();
  await expect(pane).toHaveCount(0);
  await expect(rowTitles).toHaveText(['Second page finding']);
  await expect(table.locator('[aria-sort]')).toHaveCount(0);
  expect(requestedPages).toEqual(['1', '2']);
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

test('recurring findings group exact institution names and distinguish recorded years', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await page.clock.setFixedTime(new Date(Date.now() + 2 * 60 * 60 * 1000));
  const entry = {
    county_name: 'County Assembly of Nairobi',
    query_type: 'Report on the Financial Statements',
    years_appeared: [2025, 2023, 2023],
    total_amount: 8_765_432,
    finding_ids: [101, 102],
  };
  const recurring_findings = [
    entry,
    { ...entry, query_type: 'Report on Lawfulness and Effectiveness in the Use of Public Resources', years_appeared: [2022, 2023] },
    { ...entry, county_name: 'County Executive of Nairobi' },
    { ...entry, county_name: 'National Research Institute', years_appeared: [2022, 2022] },
    { ...entry, county_name: 'Public Reading Commission', years_appeared: [] },
    ...Array.from({ length: 18 }, (_, i) => ({
      ...entry,
      county_name: `Synthetic entity ${String(i + 1).padStart(2, '0')}`,
      query_type: `UnusuallyLongPublishedHeading${'x'.repeat(90)}`,
    })),
  ];
  await page.route('**/api/v1/audit/recurring', route => route.fulfill({
    json: { recurring_findings, total: recurring_findings.length },
  }));
  await page.goto('/audits');

  const region = page.getByRole('region', { name: 'Problems reported in more than one year' });
  const assembly = region.getByText('County Assembly of Nairobi', { exact: true }).locator('..');
  await expect(assembly).toHaveCount(1);
  const statements = assembly.getByText('Financial statements', { exact: true }).locator('..');
  await expect(statements.getByText('2022 No record in this group', { exact: true })).toBeVisible();
  await expect(statements.getByText('2023 Finding recorded', { exact: true })).toBeVisible();
  await expect(statements.getByText('2025 Finding recorded', { exact: true })).toBeVisible();
  await expect(statements.getByText(/2024/)).toHaveCount(0);
  await expect(assembly.getByText('Use of public resources', { exact: true })).toBeVisible();
  await expect(region.getByText('County Executive of Nairobi', { exact: true })).toBeVisible();
  await expect(region.getByText('Showing 20 of 21', { exact: true })).toBeVisible();

  const showMore = region.getByRole('button', { name: 'Show 1 more' });
  expect((await showMore.boundingBox())?.height).toBeGreaterThanOrEqual(44);
  await showMore.press('Enter');
  await expect(region.getByText('Showing 21 of 21', { exact: true })).toBeVisible();
  await expect(region.getByText('Synthetic entity 18').locator('..').locator('li[tabindex="-1"]')).toBeFocused();

  const limited = region.getByRole('heading', { name: 'Recurring findings with fewer recorded years' }).locator('..');
  await expect(limited.getByText('National Research Institute', { exact: true })).toBeVisible();
  await expect(limited.getByText('Public Reading Commission', { exact: true })).toBeVisible();
  await expect(limited.getByText('No audit year recorded')).toBeVisible();
  await expect(region.getByText(/KES|8,765,432/)).toHaveCount(0);
  await expect(region.getByRole('link')).toHaveCount(1);
  await region.getByRole('link', { name: 'Browse all findings' }).click();
  await expect(page).toHaveURL(/#audit-findings-heading$/);
  await expect(page.getByRole('heading', { name: 'All findings', exact: true })).toBeInViewport();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBe(360);
});

test('recurring findings offer retry and preserve the server’s scope for an empty list', async ({ page }) => {
  await page.clock.setFixedTime(new Date(Date.now() + 2 * 60 * 60 * 1000));
  let failing = true;
  const reason = 'Published records have only one recorded audit year.';
  await page.route('**/api/v1/audit/recurring', route => failing
    ? route.fulfill({ status: 503, json: { detail: 'Synthetic temporary error' } })
    : route.fulfill({ json: { recurring_findings: [], total: 0, absent_reason: reason } }));
  await page.goto('/audits');
  const region = page.getByRole('region', { name: 'Problems reported in more than one year' });
  await expect(region.getByRole('alert')).toContainText(/could not be loaded|update failed/i, { timeout: 20_000 });
  await expect(region.getByText(reason)).toHaveCount(0);

  failing = false;
  await region.getByRole('button', { name: 'Try again' }).click();
  await expect(region.getByText(reason, { exact: true })).toBeVisible();
  await expect(region.getByRole('alert')).toHaveCount(0);
});

test('severity splits the published collection proportionally with accessible counts and selection', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 840 });
  await page.clock.setFixedTime(new Date(Date.now() + 2 * 60 * 60 * 1000));
  await page.route('**/api/v1/audit/summary', route => route.fulfill({ json: { total_findings: 103 } }));
  await page.route('**/api/v1/audits/statistics', route => route.fulfill({ json: {
    total_findings: 103, by_severity: { critical: 3, warning: 100 }, fiscal_years_covered: ['FY2024/25'],
  } }));
  await page.goto('/audits');
  const severity = page.getByRole('region', { name: 'Findings by severity' });
  await expect(severity.getByText('Of 103 published findings, 100 are marked Warning.')).toBeVisible();
  await expect(severity.getByText('Recorded fiscal periods FY2024/25')).toBeVisible();
  await expect(severity.getByRole('button', { name: 'Note 0' })).toBeVisible();
  await expect(severity.locator('[data-severity="info"]')).toHaveCount(0);
  const ratio = await severity.locator('[data-severity-plot]').evaluate(element => {
    const [serious, warnings] = Array.from(element.children, child => child.getBoundingClientRect().width);
    return serious / (serious + warnings);
  });
  expect(ratio).toBeCloseTo(3 / 103, 3);

  const serious = severity.getByRole('button', { name: 'Serious 3' });
  await serious.press('Enter');
  await expect(serious).toHaveAttribute('aria-pressed', 'true');
  const readout = severity.getByText('Serious · 3 of 103 published findings');
  await expect(readout).toBeVisible();
  await serious.press('Escape');
  await expect(readout).toHaveCount(0);
  await serious.click();
  await serious.click();
  await expect(serious).toHaveAttribute('aria-pressed', 'false');
  await serious.click();
  await page.getByRole('heading', { name: 'Auditor-General findings in AuditGava', exact: true }).click();
  await expect(serious).toHaveAttribute('aria-pressed', 'false');
  await expect(page.getByRole('heading', { name: 'All findings', exact: true })).toBeVisible();
});

test('severity retries unavailable and unreconciled counts and gives a distinct partial result', async ({ page }) => {
  await page.clock.setFixedTime(new Date(Date.now() + 2 * 60 * 60 * 1000));
  let stage = 0;
  await page.route('**/api/v1/audit/summary', route => route.fulfill({ json: { total_findings: 6 } }));
  await page.route('**/api/v1/audits/statistics', route => {
    if (stage === 0) return route.fulfill({ status: 503, json: { status: 'unavailable' } });
    if (stage === 1) return route.fulfill({ json: { total_findings: 7, by_severity: { warning: 7 } } });
    return route.fulfill({ json: { total_findings: 6, by_severity: { critical: 1, unknown: 5 } } });
  });
  await page.goto('/audits');
  const severity = page.getByRole('region', { name: 'Findings by severity' });
  await expect(severity.getByRole('alert')).toHaveText('Severity counts could not be loaded.');
  const retry = severity.getByRole('button', { name: 'Try again' });

  stage = 1;
  await retry.click();
  await expect(severity.getByText('The severity counts could not be matched to the published findings total above.')).toBeVisible();
  await expect(severity.locator('[data-severity-plot]')).toHaveCount(0);

  stage = 2;
  await retry.click();
  await expect(severity.getByText('Severity counts are available for 1 of 6 published findings in this collection.')).toBeVisible();
  await expect(severity.getByRole('listitem')).toHaveText('Serious 1');
  await expect(severity.locator('[data-severity-plot]')).toHaveCount(0);
  await expect(severity.getByText('Warning 0')).toHaveCount(0);
});
