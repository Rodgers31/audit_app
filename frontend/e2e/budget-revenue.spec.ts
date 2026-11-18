import { expect, test } from '@playwright/test';
import revenue from './fixtures/budget_revenue_ranked.json';

test.describe('Budget tax revenue', () => {
  test.use({ hasTouch: true, reducedMotion: 'reduce', viewport: { width: 360, height: 820 } });

  test.beforeEach(async ({ page }) => {
    await page.route('**/api/v1/budget/enhanced', route => route.fulfill({ json: { revenue_by_source: revenue } }));
    // The general SSR fixture has an empty revenue query. Exercise the page's
    // normal stale-document refetch with this test's receipt-bearing response.
    await page.clock.setFixedTime(Date.now() + 2 * 60 * 60 * 1000);
  });

  test('ranks observed collections and gives keyboard, touch and hover the same exact readout', async ({ page }) => {
    await page.goto('/budget');
    const section = page.getByRole('region', { name: 'Where tax revenue comes from' });
    await expect(section.getByText(/KRA collections, FY 2025\/26/)).toBeVisible();
    const readout = section.locator('[aria-live=polite]');
    const ranking = section.getByRole('list').first();
    const rows = ranking.getByRole('button');
    await expect(rows).toHaveCount(5);
    const customs = rows.first();
    const excise = rows.last();
    await expect(customs).toHaveAccessibleName(/Customs.*KES 981B/);
    await expect(customs).toHaveAccessibleDescription(/KES 981,125,000,000/);
    await expect(excise).toHaveAccessibleName(/Domestic excise.*-10.9%/);

    await customs.tap();
    await expect(customs).toHaveAttribute('aria-pressed', 'true');
    await expect(readout).toContainText('KES 981,125,000,000 · +12.5% year over year, as reported');
    await customs.tap();
    await expect(customs).toHaveAttribute('aria-pressed', 'false');
    await expect(readout).toBeEmpty();
    await customs.tap();
    await section.getByRole('heading').tap();
    await expect(customs).toHaveAttribute('aria-pressed', 'false');

    await customs.focus();
    await expect(readout).toContainText('KES 981,125,000,000');
    await page.keyboard.press('Enter');
    await expect(customs).toHaveAttribute('aria-pressed', 'true');
    await page.keyboard.press('Escape');
    await expect(customs).toHaveAttribute('aria-pressed', 'false');
    await expect(readout).toBeEmpty();
    await excise.hover();
    await expect(readout).toContainText('KES 65,125,000,000 · -10.9% year over year, as reported');

    await section.getByText('Read chart data', { exact: true }).tap();
    const table = section.getByRole('table');
    await expect(table.getByRole('row', { name: /Customs.*981,125,000,000/ })).toBeVisible();
    await expect(table.getByRole('row', { name: /Agency Revenue|Other Tax/ })).toHaveCount(0);
    await page.getByRole('button', { name: 'FY2024/25', exact: true }).tap();
    await expect(page.getByRole('heading', { name: 'KES 150B approved for FY 2024/25' })).toBeVisible();
    await expect(section.getByText(/KRA collections, FY 2025\/26/)).toBeVisible();
  });

  test('opens one source sheet and retains edition, reconciliation, totals and exact historical data', async ({ page }) => {
    await page.goto('/budget');
    const section = page.getByRole('region', { name: 'Where tax revenue comes from' });
    const chip = section.getByRole('button', { name: 'Source: KRA annual performance (dashboard edition)' });
    await expect(section.locator('button[aria-haspopup=dialog]')).toHaveCount(1);
    await chip.tap();
    const dialog = page.getByRole('dialog', { name: 'Sources for tax collections' });
    await expect(dialog.getByText('Source cited, with a caveat', { exact: true })).toBeVisible();
    await expect(dialog.getByText('Total Agency Revenue', { exact: true })).toBeVisible();
    await expect(dialog.getByText('KES 125,500,000,000 · Publisher-stated', { exact: true })).toBeVisible();
    await expect(dialog.getByText('Edition dashboard_bundle').first()).toBeHidden();
    await dialog.getByText('Technical details', { exact: true }).tap();
    await expect(dialog.getByText('PAYE · KES 550,250,000,000 · Derived amount')).toBeVisible();
    await expect(dialog.getByText(/Dashboard version; not independently reconciled/).first()).toBeVisible();
    await expect(dialog.getByText(/Publication date unavailable/).first()).toBeVisible();
    await expect(dialog.getByText(/Locator:.*collections.customs/)).toBeVisible();
    await expect(dialog.getByText(/Residual withheld because Customs includes agency levies/)).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(dialog).toBeHidden();
    await expect(chip).toBeFocused();
  });
});
