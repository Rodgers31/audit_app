import { expect, test } from '@playwright/test';

const stockSource = 'https://www.centralbank.go.ke/synthetic-statement.pdf';
const dsaSource = 'https://www.imf.org/synthetic-dsa.pdf';

test('Home keeps the register, WEO ratio and dated DSA distinct in their receipts', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 840 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.clock.setFixedTime(new Date(Date.now() + 2 * 60 * 60 * 1000));
  await page.route(url => url.pathname === '/api/v1/debt/timeline', route => route.fulfill({ json: {
    status: 'success', timeline: [{
      year: 2026, unit: 'KES', total: 13_097_471_100_000, domestic: 7e12, external: 6097471100000,
      gdp_ratio: null, gdp: null, qualifications: { total: {
        status: 'verified', document_bytes_checked: true, value_checked: true, source_kind: 'pdf',
        source_document_id: 1, receipt_id: 1, digest: 'a'.repeat(64),
        identity: { measure: 'total', entity_id: null, geography: 'KEN', period: '2026', unit: 'KES', basis: 'actual' },
        source_url: stockSource, locator: { cell: '2026-06 / total', page: 56, table: 'Table 4.1.3' },
      } },
    }],
  } }));
  await page.route(url => url.pathname === '/api/v1/debt/national', route => route.fulfill({ json: {
    status: 'success', data: {
      total_outstanding: 12_996_438_428_526.28, loan_count: 51,
      categories: { external_bilateral: { loan_count: 49, total_outstanding: 12_996_438_428_526.28 },
        pending_bills: { loan_count: 2, total_outstanding: 475500000000 } },
      debt_to_gdp_ratio: 71.3, debt_to_gdp_year: 2025, debt_to_gdp_source: 'IMF World Economic Outlook',
      debt_to_gdp_basis: 'IMF General Government Gross Debt (GGXWDG_NGDP)', debt_to_gdp_vintage: '2026-10-27T04:38:48Z',
      figure_qualifications: { derived_ratio: { status: 'qualified', reason: 'published_imf_ratio_outside_seven_table_contract' } },
      debt_sustainability: { imf_dsa: { overall_risk_of_debt_distress: 'High', risk_of_external_debt_distress: 'High',
        source: { series: 'Synthetic IMF Country Report', url: dsaSource, dsa_date: '2024-10-18', page: 132 },
        freshness: { status: 'confirmation_aging' },
      } },
    },
  } }));
  await page.goto('/');
  const region = page.getByRole('region', { name: 'Headline public finance figures' });
  await expect(region.getByRole('heading', { level: 3 })).toHaveText(['Debt in the loans register', 'Debt-to-GDP', 'Debt distress risk']);
  await expect(region.locator('[data-summary-debt]')).toContainText('KES 13.00T');
  await expect(region.locator('[data-summary-debt]')).toContainText('Sum of 49 loan rows, pending bills excluded · No single reporting date');
  await expect(region.locator('[data-summary-ratio]')).toContainText('KES 71.3 for every KES 100 of 2025 economic output');
  await expect(region.locator('[data-summary-dsa]')).toContainText('18 October 2024 · current status unverified');
  await expect(region).not.toContainText('55%');
  await expect(region.locator('[data-summary-ratio] .audit-figure')).toHaveCSS('color', 'rgb(16, 27, 20)');
  await expect(region.locator('[data-summary-dsa] .audit-figure')).toHaveCSS('color', 'rgb(158, 47, 38)');

  const register = region.getByRole('button', { name: /Evidence for debt register operands/i });
  await register.press('Enter');
  const registerReceipt = page.getByRole('dialog', { name: /debt register operands/i });
  await expect(registerReceipt.getByText(/Exact total KES 12,996,438,428,526.28/)).toBeVisible();
  await expect(registerReceipt.getByText(/separately reports KES 13,097,471,100,000 for June 2026/)).toBeVisible();
  await expect(registerReceipt.getByRole('link', { name: /Central Bank debt observation/ })).toHaveAttribute('href', stockSource + '#page=56');
  await registerReceipt.press('Escape');
  await expect(register).toBeFocused();
  await region.getByRole('button', { name: /Evidence for Debt distress risk/ }).click();
  const riskReceipt = page.getByRole('dialog', { name: 'Debt distress risk' });
  await expect(riskReceipt.getByRole('link', { name: 'IMF–World Bank DSA, Oct 2024' })).toHaveAttribute('href', dsaSource + '#page=132');
});
