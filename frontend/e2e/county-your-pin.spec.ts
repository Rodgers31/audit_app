import { expect, test, type Page } from '@playwright/test';
import { countyResponse } from './utils/countyResponse';

const preferenceKey = 'auditgava:last-viewed-county';
const yourCounty = (page: Page) => page.getByRole('link', { name: /^Your county /i });
const preference = (page: Page) => page.evaluate(key => localStorage.getItem(key), preferenceKey);
const yearPicker = (page: Page) => page.getByText('Year', { exact: true }).locator('..').getByRole('combobox');
const countyHeading = (page: Page) => page.getByRole('heading', { level: 1 });

test('search precedes the pin, and opening a county survives Back and reload', async ({ browserName, page }) => {
  await page.goto('/counties?view=all');
  const searches = page.getByRole('searchbox', { name: 'Search County' });
  await expect(searches).toBeVisible();
  await expect(yourCounty(page)).toHaveCount(0);
  await searches.fill('Baringo');
  const countyLink = page.getByRole('link', { name: 'Baringo', exact: true }).first();
  await expect(countyLink).toBeVisible();
  expect(await preference(page)).toBeNull();

  await countyLink.click();
  await expect(countyHeading(page)).toHaveText('Baringo County');
  await expect.poll(() => preference(page)).toBe('baringo');
  await page.goBack();
  await expect(page).toHaveURL(/\/counties\?view=all/);
  await expect(yourCounty(page)).toContainText('Baringo');
  await page.reload();
  const pin = yourCounty(page);
  await expect(pin).toContainText('Baringo');
  await expect(pin).toHaveAttribute('href', /\/counties\/baringo(?:\?|$)/);

  await searches.focus();
  // Safari on macOS includes links in keyboard navigation with Option-Tab.
  await page.keyboard.press(browserName === 'webkit' && process.platform === 'darwin' ? 'Alt+Tab' : 'Tab');
  await expect(pin).toBeFocused();
  const bounds = await pin.boundingBox();
  expect(bounds?.height).toBeGreaterThanOrEqual(44);
  await pin.press('Enter');
  await expect(countyHeading(page)).toHaveText('Baringo County');
});

test('stores canonical county identity for aliases and preserves the last valid detail after an error', async ({ page }) => {
  await page.goto('/counties/Murang%E2%80%99a');
  await expect(countyHeading(page)).toHaveText("Murang'a County");
  await expect.poll(() => preference(page)).toBe('Murang%27a');
  await page.goto('/counties/unknown-county');
  await expect(page.getByText(/failed to load county/i)).toBeVisible();
  expect(await preference(page)).toBe('Murang%27a');
  await page.goto('/counties');
  await expect(yourCounty(page)).toHaveAttribute('href', /\/counties\/Murang%27a(?:\?|$)/);

  await page.goto('/counties/code%3A001');
  await expect(countyHeading(page)).toHaveText('Mombasa County');
  await expect.poll(() => preference(page)).toBe('mombasa');
  await page.goto('/counties');
  await expect(yourCounty(page)).toContainText('Mombasa');
});

test('uses a qualified spending value only for the active fiscal period', async ({ page }) => {
  await page.goto('/counties/030');
  await expect(countyHeading(page)).toHaveText('Baringo County');
  await expect.poll(() => preference(page)).toBe('baringo');

  await countyResponse(page, async route => {
    const response = await route.fetch();
    const data = await response.json() as Array<{ name: string; id: string } & Record<string, unknown>>;
    const evidence = (measure: string, id: string) => ({
      status: 'qualified', reason: 'historical_source_not_value_checked', source_kind: 'pdf',
      identity: {
        measure, entity_id: Number(id), geography: 'Baringo County', period: 'FY2024/25', unit: 'KES', basis: 'actual',
        dimensions: { category: 'Total', subcategory: null },
      },
      source_document_id: 30, publisher: 'Controller of Budget', source_url: 'https://cob.go.ke/synthetic-budget-review.pdf',
    });
    await route.fulfill({ json: data.map(county => county.name !== 'Baringo' ? county : {
      ...county, budget_source: 'cob_cbirr', budget_utilization: 76,
      financial_health_score: 2, audit_status: 'qualified',
      figure_qualifications: { budget_lines: {
        '1': { allocated_amount: evidence('allocated_amount', county.id), actual_spent: evidence('actual_spent', county.id) },
      } },
    }) });
  });

  const pin = yourCounty(page);
  await expect(pin).toContainText('76% spent');
  await expect(pin).toHaveAttribute('href', '/counties/baringo?fy=FY2024%2F25');
  await expect(pin).not.toContainText(/audit record|qualified/i);
  await yearPicker(page).selectOption('FY2025/26 9M');
  await expect(pin).toHaveAttribute('href', '/counties/baringo?fy=FY2025%2F26%209M');
  await expect(pin).not.toContainText(/spent/i);
});

test('blocked browser storage leaves search and county detail available without a pin', async ({ page }) => {
  await page.addInitScript(key => {
    const get = Storage.prototype.getItem;
    const set = Storage.prototype.setItem;
    Storage.prototype.getItem = function (name) {
      if (name === key) throw new DOMException('Blocked', 'SecurityError');
      return get.call(this, name);
    };
    Storage.prototype.setItem = function (name, value) {
      if (name === key) throw new DOMException('Blocked', 'SecurityError');
      return set.call(this, name, value);
    };
  }, preferenceKey);
  await page.goto('/counties/030');
  await expect(countyHeading(page)).toHaveText('Baringo County');
  await page.goto('/counties');
  await expect(page.getByRole('searchbox', { name: 'Search County' })).toBeVisible();
  await expect(yourCounty(page)).toHaveCount(0);
});
