import { expect, test, type Page } from '@playwright/test';
import { syntheticEconomicContext } from '../test/fixtures/budgetEconomicContext';

async function openContext(page: Page, overrides = {}) {
  await page.route('**/api/v1/budget/enhanced', route => route.fulfill({
    json: { economic_context: { ...syntheticEconomicContext, ...overrides } },
  }));
  // Refetch the SSR response through the same stale-document path as a live visit.
  await page.clock.setFixedTime(Date.now() + 2 * 60 * 60 * 1000);
  await page.goto('/budget');
  const section = page.getByRole('region', { name: 'Economic context' });
  await expect(section.getByText('KES 12.35T')).toBeVisible();
  return section;
}

test.describe('Budget economic context', () => {
  test.use({ hasTouch: true, reducedMotion: 'reduce', viewport: { width: 360, height: 820 } });

  test('states the missing ratio, cites the matched target and exposes the GDP receipt with focus return', async ({ page }) => {
    const section = await openContext(page);
    await expect(section.getByRole('heading', { level: 3 })).toHaveText(['GDP', 'Budget / GDP', 'Inflation']);
    await expect(section.getByText('A comparable GDP figure for the same fiscal year is unavailable.', { exact: true }).first()).toBeVisible();
    await expect(section.getByText(/32\.1%|15\.2%/)).toHaveCount(0);
    await expect(section.getByText('At current prices in calendar year 2025.')).toBeVisible();
    await expect(section.getByText('Real GDP growth in 2024: -0.4%.')).toBeVisible();
    await expect(section.getByText('7.51%', { exact: true })).toBeVisible();
    await expect(section.getByText('Above target', { exact: true })).toBeVisible();
    await expect(section.getByRole('link', { name: /CBK Monetary Policy Statement.*p\. 18/ })).toHaveAttribute('href', /centralbank\.go\.ke\/.*#page=25$/);

    const receipt = section.getByRole('button', { name: /Evidence for GDP$/ });
    await receipt.tap();
    const dialog = section.getByRole('dialog');
    await expect(dialog.getByText('GDP at current prices was KES 12,345,678,000,000 in calendar year 2025.')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(dialog).toBeHidden();
    await expect(receipt).toBeFocused();
  });

  test('leaves the annual average separate from the target even when it is numerically higher', async ({ page }) => {
    const section = await openContext(page, {
      inflation_pct: 8.2, inflation_as_of: '2026-12-31', inflation_measure: 'CPI inflation, annual average',
    });
    await expect(section.getByText('8.2%', { exact: true })).toBeVisible();
    await expect(section.getByText('Annual average CPI inflation · 2026')).toBeVisible();
    await expect(section.getByText('Above target', { exact: true })).toHaveCount(0);
    await expect(section.getByRole('link', { name: /CBK Monetary Policy/ })).toHaveCount(0);
  });
});
