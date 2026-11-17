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
