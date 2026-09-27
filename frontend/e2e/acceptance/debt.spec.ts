import { expect, Page, test } from '@playwright/test';

// The acceptance fixture API refuses the server's national-debt prefetch.
// Each test can therefore supply a browser observation without SSR caching
// hiding the input. All other routes use the shared fixture-backed API.
async function nationalObservation(page: Page, patch: Record<string, unknown> = {}) {
  await page.route('**/api/v1/debt/national', (route) => route.fulfill({
    contentType: 'application/json',
    json: {
      status: 'success',
      data: {
        total_outstanding: 12_000_000_000_000,
        gdp: 20_000_000_000_000,
        debt_to_gdp_ratio: 69.3,
        debt_to_gdp_year: 2025,
        debt_to_gdp_basis: 'IMF General Government Gross Debt, % of GDP (GGXWDG_NGDP) — vintage-consistent',
        debt_to_gdp_source: 'IMF World Economic Outlook',
        categories: {},
        summary: {},
        debt_sustainability: {
          imf_dsa: {
            overall_risk_of_debt_distress: 'High',
            risk_of_external_debt_distress: 'High',
            source: {
              series: 'IMF Country Report No. 24/316',
              url: 'https://www.imf.org/-/media/files/publications/cr/2024/english/1kenea2024003-print-pdf.pdf',
              page: 132,
              dsa_date: '2024-10-18',
              published: '2024-11-01',
            },
            latest_confirmed: { as_of: '2026-03-31' },
          },
        },
        ...patch,
      },
    },
  }));
}

test('debt page separates the nominal observation from the dated DSA', async ({ page }) => {
  await nationalObservation(page);
  await page.goto('/debt');
  const ratio = page.getByText('Debt-to-GDP', { exact: true }).locator('..');
  await expect(ratio).toContainText('69.3%');
  await expect(ratio).toContainText('Nominal debt');
  await expect(ratio).toContainText('IMF World Economic Outlook');
  await expect(ratio).toContainText('Observation: 2025');
  await expect(page.getByText('vs PFM Act 55%')).toHaveCount(0);
  await expect(ratio.locator('[style*="background"]')).toHaveCount(0);
  await expect(page.getByText('High', { exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'IMF–World Bank DSA, Oct 2024' }))
    .toHaveAttribute('href', /#page=132$/);
  await expect(page.getByText(/Published 1 Nov 2024/)).toContainText('31 Mar 2026');
});

test('missing ratio and assessment stay absent despite register and GDP inputs', async ({ page }) => {
  await nationalObservation(page, { debt_to_gdp_ratio: null, debt_sustainability: {} });
  await page.goto('/debt');
  const ratio = page.getByText('Debt-to-GDP', { exact: true }).locator('..');
  await expect(ratio).toContainText('Not published');
  await expect(ratio).not.toContainText('60.0%');
  await expect(page.getByText('Not assessed', { exact: true })).toBeVisible();
  await expect(page.getByText('vs PFM Act 55%')).toHaveCount(0);
});

test('a published zero remains zero without a risk band', async ({ page }) => {
  await nationalObservation(page, { debt_to_gdp_ratio: 0, debt_sustainability: {} });
  await page.goto('/debt');
  const ratio = page.getByText('Debt-to-GDP', { exact: true }).locator('..');
  await expect(ratio).toContainText('0.0%');
  await expect(ratio.locator('[style*="background"]')).toHaveCount(0);
  await expect(page.getByText('Not assessed', { exact: true })).toBeVisible();
});
