/**
 * Side-by-side county comparison (/counties/compare?ids=...)
 */
import { devices, expect, test } from '@playwright/test';
import { pageShell, waitForAppReady } from './utils/selectors';

test.describe('/counties/compare', () => {
  test('empty state prompts user to pick ≥2 counties', async ({ page }) => {
    await page.goto('/counties/compare');
    await waitForAppReady(page);

    await expect(pageShell.h1(page)).toContainText(/Compare counties|Linganisha Kaunti/i);
    await expect(
      page.getByText(/Pick at least two counties|Chagua angalau kaunti mbili/i)
    ).toBeVisible({ timeout: 15_000 });
  });

  test('deep link with ?ids=… pre-populates the table', async ({ page }) => {
    await page.goto('/counties/compare?ids=047,001,032');
    await waitForAppReady(page);

    // Table column headers should include each county
    await expect(page.getByRole('columnheader', { name: /Mombasa/i }).first()).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole('columnheader', { name: /Nairobi/i }).first()).toBeVisible();
    await expect(page.getByRole('columnheader', { name: /Nakuru/i }).first()).toBeVisible();

    for (const label of ['Budget', 'Spent (%)', 'Debt', 'Published findings', 'Serious findings']) {
      await expect(page.getByRole('rowheader', { name: new RegExp(label.replace(/[()]/g, '\\$&')) })).toBeVisible();
    }
    const details = page.locator('summary').filter({ hasText: 'More measures' });
    await details.click();
    const additional = page.getByRole('table', { name: 'More measures' });
    for (const label of ['Population', 'Development share', 'Financial health score']) {
      await expect(additional.getByRole('rowheader', { name: new RegExp(label) })).toBeVisible();
    }
  });

  test('county names in the table link to detail pages', async ({ page }) => {
    await page.goto('/counties/compare?ids=047,001');
    await waitForAppReady(page);

    const mombasaLink = page.getByRole('link', { name: /^Mombasa$/ }).first();
    await expect(mombasaLink).toBeVisible({ timeout: 15_000 });
    const href = await mombasaLink.getAttribute('href');
    expect(href).toMatch(/\/counties\/[\w-]+/);
  });
});

test.describe('county comparison picker interactions', () => {
  test('searches with the keyboard and prevents the same county appearing twice', async ({ page }) => {
    await page.goto('/counties/compare?ids=047,047');
    const first = page.getByRole('combobox', { name: 'County 1' });
    const second = page.getByRole('combobox', { name: 'County 2' });
    await expect(first).toHaveValue('Mombasa');
    await expect(second).toHaveValue('');
    await expect(page.getByRole('note')).toHaveCount(0);

    await second.focus();
    await second.pressSequentially('Mombasa');
    await expect(page.getByRole('status').filter({ hasText: 'No counties match.' })).toBeVisible();
    await expect(page.getByRole('option', { name: 'Mombasa' })).toHaveCount(0);
    await second.press('Escape');
    await expect(second).toBeFocused();
    await expect(second).toHaveValue('');
    await second.fill('NAÍROBI County');
    await second.press('ArrowDown');
    await expect(page.getByRole('option', { name: 'Nairobi' })).toHaveAttribute('aria-selected', 'true');
    await second.press('Enter');
    await expect(second).toHaveValue('Nairobi');
    await expect(second).toBeFocused();
    await expect(page).toHaveURL(/ids=047,001$/);
    await expect(page.getByRole('button', { name: 'Debt and pending bills' })).toBeVisible();
    await expect(page.getByText(/Tap or select a county name/)).toBeVisible();
    await page.reload();
    await expect(second).toHaveValue('Nairobi');
    await expect(page.getByRole('table')).toBeVisible();

    await second.focus();
    await second.press('ArrowUp');
    await expect(page.getByRole('option', { name: 'Clear county' })).toHaveAttribute('aria-selected', 'true');
    await second.press('Enter');
    await expect(second).toHaveValue('');
    await expect(page).toHaveURL(/ids=047$/);
  });

  test('suggested pair buttons select the linked county IDs in order', async ({ page }) => {
    await page.goto('/counties/compare');

    for (const [first, second] of [['Nairobi', 'Kiambu'], ['Turkana', 'Marsabit']]) {
      await page.getByRole('button', { name: `${first} vs ${second}` }).click();
      const table = page.getByRole('table', { name: 'County comparison' });
      const firstLink = table.getByRole('link', { name: first, exact: true });
      const secondLink = table.getByRole('link', { name: second, exact: true });
      await expect(firstLink).toBeVisible();
      await expect(secondLink).toBeVisible();
      const ids = await Promise.all([firstLink, secondLink].map(async (link) => (await link.getAttribute('href'))?.split('/').at(-1)));
      await expect(page).toHaveURL(new RegExp(`ids=${ids.join(',')}$`));
      await expect(page.getByRole('combobox', { name: 'County 1' })).toHaveValue(first);
      await expect(page.getByRole('combobox', { name: 'County 2' })).toHaveValue(second);
    }
  });

  test('supports phone taps and adding and removing a third county', async ({ browser }, testInfo) => {
    test.skip(testInfo.project.name === 'firefox', 'Firefox does not support Playwright mobile emulation.');
    const phone = await browser.newContext({
      ...devices['iPhone 13'],
      viewport: { width: 360, height: 800 },
      reducedMotion: 'reduce',
      baseURL: testInfo.project.use.baseURL,
    });
    try {
      const page = await phone.newPage();
      await page.goto('/counties/compare?ids=047,001');
      const first = page.getByRole('combobox', { name: 'County 1' });
      const second = page.getByRole('combobox', { name: 'County 2' });
      await expect(first).toHaveValue('Mombasa');
      await expect(second).toHaveValue('Nairobi');
      const firstBox = (await first.boundingBox())!;
      const secondBox = (await second.boundingBox())!;
      expect(firstBox.y).toBe(secondBox.y);
      expect(firstBox.x + firstBox.width).toBeLessThan(secondBox.x);
      expect(firstBox.height).toBeGreaterThanOrEqual(44);
      await expect(first).toHaveCSS('font-size', '16px');

      await page.getByRole('button', { name: 'Add a county' }).tap();
      const third = page.getByRole('combobox', { name: 'County 3' });
      await expect(third).toBeFocused();
      await third.fill('Nakuru');
      await page.getByRole('option', { name: 'Nakuru' }).tap();
      await expect(third).toHaveValue('Nakuru');
      await expect(page).toHaveURL(/ids=047,001,032$/);
      const debtInfo = page.getByRole('button', { name: 'Debt and pending bills' });
      await debtInfo.tap();
      const dialog = page.getByRole('dialog', { name: 'Debt and pending bills' });
      await expect(dialog).toBeVisible();
      await expect(dialog.getByText(/trade payables/)).toBeVisible();
      await dialog.getByRole('button', { name: 'Close', exact: true }).tap();
      await expect(debtInfo).toBeFocused();

      await page.getByRole('button', { name: 'Remove county 3' }).tap();
      await expect(third).toHaveCount(0);
      await expect(second).toBeFocused();
      await expect(page).toHaveURL(/ids=047,001$/);
    } finally {
      await phone.close();
    }
  });
});


test.describe('county comparison ledger', () => {
  test('fits two county columns at 360px and pins the measure while a third scrolls', async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 900 });
    await page.goto('/counties/compare?ids=047,001');
    const table = page.getByRole('table', { name: 'County comparison' });
    const wrapper = table.locator('..');
    await expect(table).toBeVisible();
    const box = (await wrapper.boundingBox())!;
    const nairobi = (await table.getByRole('columnheader', { name: 'Nairobi' }).boundingBox())!;
    expect(nairobi.x + nairobi.width).toBeLessThanOrEqual(box.x + box.width);
    expect(await wrapper.evaluate((el) => el.scrollWidth)).toBeLessThanOrEqual(box.width);

    await page.goto('/counties/compare?ids=047,001,032');
    await expect(wrapper).toHaveAttribute('tabindex', '0');
    await expect(wrapper).toHaveAttribute('role', 'region');
    const pinned = table.getByRole('rowheader', { name: 'Budget', exact: true });
    const before = (await pinned.boundingBox())!;
    await wrapper.focus();
    await wrapper.press('ArrowRight');
    await expect.poll(() => wrapper.evaluate((el) => el.scrollLeft)).toBeGreaterThan(0);
    expect((await pinned.boundingBox())!.x).toBe(before.x);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(360);
    await expect(page.getByRole('button', { name: 'Add a county' })).toBeHidden();
  });

  test('adds and shares a fourth desktop county and preserves the link on a smaller screen', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto('/counties/compare?ids=047,001,032');
    await page.getByRole('button', { name: 'Add a county' }).click();
    const fourth = page.getByRole('combobox', { name: 'County 4' });
    await expect(fourth).toBeFocused();
    await fourth.fill('Kiambu');
    await fourth.press('Enter');
    const table = page.getByRole('table', { name: 'County comparison' });
    await expect(table.getByRole('columnheader', { name: 'Kiambu' })).toBeVisible();
    const fourthId = (await table.getByRole('link', { name: 'Kiambu' }).getAttribute('href'))!.split('/').at(-1);
    await expect(page).toHaveURL(new RegExp(`ids=047,001,032,${fourthId}$`));

    const share = page.getByRole('button', { name: 'Share this comparison' });
    await share.focus();
    await share.press('Enter');
    const dialog = page.getByRole('dialog', { name: 'Share this comparison' });
    const link = dialog.getByRole('textbox', { name: 'Comparison link' });
    await expect(link).toHaveValue(page.url());
    await dialog.getByRole('button', { name: 'Copy link' }).click();
    await expect(dialog.getByRole('status')).toHaveText(/Link copied|Select and copy/);
    await page.keyboard.press('Escape');
    await expect(share).toBeFocused();

    await page.setViewportSize({ width: 360, height: 900 });
    await page.reload();
    await expect(fourth).toHaveValue('Kiambu');
    await expect(table.locator('..')).toHaveAttribute('tabindex', '0');
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(360);
  });

  test('compares qualified figures, identifies measured zero and keeps audit coverage separate', async ({ page }) => {
    await page.clock.setFixedTime(new Date(Date.now() + 3_600_001));
    await page.route(url => url.pathname === '/api/v1/counties' && url.searchParams.get('limit') === '50', async (route) => {
      const response = await route.fetch();
      const counties: Array<{ id: string }> = await response.json();
      const data = counties.map((county) => {
        if (county.id !== '001' && county.id !== '047') return county;
        const first = county.id === '047';
        return {
          ...county,
          audit_findings_count: first ? 25 : 0,
          audit_issues: Array.from({ length: 10 }, () => ({ severity: 'critical' })),
          debt: first ? 1_000_000 : 0,
          total_debt_absent_reason: null,
          debt_currency: 'KES',
          debt_basis: 'actual',
          debt_accounting_basis: 'selected_instrument_outstanding',
          debt_as_at: '2025-06-30',
          debt_coverage: 'selected_eligible_instruments_only',
          financial_summary: {
            total_allocation: first ? 2_000_000 : 1_000_000,
            total_spent: first ? 1_400_000 : 0,
            execution_rate: first ? 70 : 0,
            currency: 'KES',
            accounting_basis: 'reported_total',
            fiscal_period: { label: 'FY 2024/25', start_date: '2024-07-01', end_date: '2025-06-30' },
            sources: [{ url: 'https://www.treasury.go.ke/synthetic-browser-fixture.pdf' }],
          },
          pending_bills: first ? 200 : null,
          pending_bills_as_at: first ? '2025-06-30' : null,
          pending_bills_source: first ? {
            title: 'Synthetic pending bills report',
            table: 'Table 2',
            url: 'https://www.treasury.go.ke/synthetic-browser-fixture.pdf',
          } : null,
        };
      });
      await route.fulfill({ response, json: data });
    });
    await page.goto('/counties/compare?ids=047,001');
    const table = page.getByRole('table', { name: 'County comparison' });
    await expect(table.getByRole('columnheader', { name: 'FY 2024/25' })).toBeVisible();
    const row = (name: string) => table.getByRole('row').filter({ has: page.getByRole('rowheader', { name, exact: true }) });
    await expect(row('Budget').getByText('Highest')).toBeVisible();
    await expect(row('Spent (%)').getByText('0.0%', { exact: true })).toBeVisible();
    await expect(row('Spent (%)').getByText('Lowest')).toBeVisible();
    await expect(row('Published findings').getByText('25', { exact: true })).toBeVisible();
    await expect(row('Published findings').getByText('0', { exact: true })).toBeVisible();
    await expect(row('Serious findings').getByRole('cell', { name: 'Unavailable' })).toHaveCount(2);
    await expect(page.getByRole('button', { name: 'Debt and pending bills' })).toBeVisible();
    await page.getByRole('button', { name: 'Debt and pending bills' }).click();
    const info = page.getByRole('dialog', { name: 'Debt and pending bills' });
    await expect(info.getByRole('link', { name: 'Synthetic pending bills report' })).toHaveAttribute('href', 'https://www.treasury.go.ke/synthetic-browser-fixture.pdf');
    await expect(info.getByText(/A dated zero balance/)).toBeVisible();
  });
});
