import { expect, test, type Page } from '@playwright/test';
import { registerApiMocks } from './utils/mockApi';

const lender = 'Synthetic Procurement Bank (Water & Energy)';
const otherLender = 'Separate Fixture Lender';
const reportPath = '/public-search-browser-report.pdf#page=17';
const findingsPath = /\/api\/v1\/audit\/findings\?/;

async function mockResults(page: Page) {
  await registerApiMocks(page);
  const loans = [lender, otherLender].map((name, index) => ({
    id: index + 1, lender: name, lender_type: 'external_multilateral',
    outstanding_numeric: 1000 - index, interest_rate_pct: null, annual_service_cost: null,
  }));
  await page.route('**/api/v1/debt/loans', route => route.fulfill({
    json: { loans, total_loans: loans.length },
  }));
  await page.route(findingsPath, route => {
    const { origin, searchParams } = new URL(route.request().url());
    expect(Object.fromEntries(searchParams)).toEqual({ page: '1', limit: '100' });
    return route.fulfill({ json: {
      items: [
        { id: 1, finding_title: 'Procurement controls', finding_text: 'Supporting records were absent.',
          audited_entity_name: 'Synthetic public works office', page_ref: 'p. 17',
          source_document_url: origin + reportPath },
        { id: 2, finding_title: 'Procurement Without A Cited Page', finding_text: 'Supporting records were absent.',
          page_ref: 'Annex A', source_document_url: origin + reportPath },
      ],
      page: 1, limit: 100, total: 2,
    } });
  });
}

test('compact search result groups reflow in light and dark across the six approved widths', async ({ page }, testInfo) => {
  await mockResults(page);
  await page.goto('/public-search-browser-missing-page');
  const search = page.getByRole('main').getByRole('search', { name: 'Search AuditGava' });
  const field = search.getByRole('searchbox');
  await expect(field).toHaveAttribute('placeholder', 'Search counties, findings, terms');
  await field.fill('procurement');
  const result = search.getByRole('link', { name: /Procurement controls.*Open cited report page/ });
  const lenderLink = search.getByRole('link', { name: /Synthetic Procurement Bank.*Open loan register/ });
  await expect(result).toHaveAttribute('href', new RegExp(reportPath.replace('.', '\\.')));
  await expect(lenderLink).toHaveAttribute('href', '/debt?lender=Synthetic+Procurement+Bank+%28Water+%26+Energy%29#loan-register');
  await expect(search.getByRole('link', { name: /without a cited page/i })).toHaveCount(0);

  for (const colorScheme of ['light', 'dark'] as const) {
    await page.emulateMedia({ colorScheme, reducedMotion: 'reduce' });
    if (colorScheme === 'dark') await expect(page.locator('html')).toHaveClass(/\bdark\b/);
    else await expect(page.locator('html')).not.toHaveClass(/\bdark\b/);
    for (const width of [360, 390, 768, 1024, 1280, 1440]) {
      await page.setViewportSize({ width, height: 850 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
      for (const target of [field, search.getByRole('button', { name: 'Clear search' }), result, lenderLink]) {
        const box = await target.boundingBox();
        expect(box?.width).toBeGreaterThanOrEqual(44);
        expect(box?.height).toBeGreaterThanOrEqual(44);
      }
      expect(await search.evaluate(node => node.scrollWidth)).toBe(await search.evaluate(node => node.clientWidth));
      if ([360, 768, 1440].includes(width)) {
        await search.screenshot({ path: testInfo.outputPath(`compact-search-${colorScheme}-${width}.png`) });
      }
    }
  }
});

test('a keyboard user can open the lender link and reaches the filtered register', async ({ page, browserName }) => {
  await mockResults(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/learn');
  const trigger = page.getByRole('banner').getByRole('button', { name: 'Search AuditGava' });
  await expect(trigger).toBeEnabled();
  await trigger.focus();
  await page.keyboard.press('Enter');
  const dialog = page.getByRole('dialog', { name: 'Search AuditGava' });
  const field = dialog.getByRole('searchbox');
  await expect(field).toBeFocused();
  await field.fill('Synthetic Procurement Bank');
  const link = dialog.getByRole('link', { name: /Synthetic Procurement Bank.*Open loan register/ });
  await expect(link).toBeVisible();
  // WebKit's default macOS keyboard navigation includes links with Option-Tab.
  const tab = browserName === 'webkit' && process.platform === 'darwin' ? 'Alt+Tab' : 'Tab';
  await page.keyboard.press(tab);
  await expect(dialog.getByRole('button', { name: 'Clear search' })).toBeFocused();
  await page.keyboard.press(tab);
  await expect(link).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/\/debt\?lender=.*#loan-register$/);
  const register = page.locator('#loan-register');
  const filter = register.getByRole('searchbox', { name: 'Search lender names' });
  await expect(filter).toHaveValue(lender);
  await expect(register.getByRole('row', { name: /Synthetic Procurement Bank/ })).toBeVisible();
  await expect(register.getByRole('row', { name: /Separate Fixture Lender/ })).toHaveCount(0);
  await filter.fill('');
  await expect(register.getByRole('row', { name: /Separate Fixture Lender/ })).toBeVisible();
});

test.describe('touch search', () => {
  test.use({ viewport: { width: 390, height: 840 }, hasTouch: true, reducedMotion: 'reduce' });

  test('retains county results when the audit source fails and clears the query with focus restored', async ({ page }) => {
    await mockResults(page);
    await page.route(findingsPath, route => route.fulfill({ status: 503, json: { detail: 'Fixture outage' } }));
    await page.goto('/learn');
    await page.getByRole('button', { name: 'Open navigation menu' }).tap();
    const drawer = page.getByRole('dialog', { name: 'Mobile navigation' });
    const field = drawer.getByRole('searchbox');
    await field.tap();
    await field.fill('Baringo');
    await expect(drawer.getByRole('link', { name: 'Baringo', exact: true })).toHaveAttribute('href', '/counties/baringo');
    await expect(drawer.getByRole('status')).toContainText('Audit findings search is unavailable.');
    await drawer.getByRole('button', { name: 'Clear search' }).tap();
    await expect(field).toHaveValue('');
    await expect(field).toBeFocused();
    await expect(drawer.getByRole('link', { name: 'Baringo', exact: true })).toHaveCount(0);
  });

  test('opens the cited report page with a native touch link', async ({ page }) => {
    await mockResults(page);
    await page.route('**/public-search-browser-report.pdf', route => route.fulfill({
      contentType: 'text/plain', body: 'Synthetic cited report fixture',
    }));
    await page.goto('/learn');
    await page.getByRole('button', { name: 'Open navigation menu' }).tap();
    const drawer = page.getByRole('dialog', { name: 'Mobile navigation' });
    const field = drawer.getByRole('searchbox');
    await field.tap();
    await field.fill('procurement');
    await drawer.getByRole('link', { name: /Procurement controls.*Open cited report page/ }).tap();
    await expect(page).toHaveURL(new RegExp(reportPath.replace('.', '\\.')));
    await expect(page.locator('body')).toHaveText('Synthetic cited report fixture');
  });
});
