/**
 * Unaccounted Funds (/accountability/unaccounted-funds, formerly /missing-funds)
 *
 * Lists findings the Auditor-General's report itself heads "Unaccounted …" or
 * "Loss of Funds", each linked to its page (issue #233). It publishes no money
 * total in any state. Explicit synthetic responses exercise both populated and empty states.
 */
import { expect, test } from '@playwright/test';
import { pageShell, waitForAppReady } from './utils/selectors';

const PATH = '/accountability/unaccounted-funds';

async function findings(page: import('@playwright/test').Page, populated: boolean) {
  const cases = populated ? [{ finding_id: 901, entity: 'Synthetic County Assembly', entity_type: 'county',
    county_name: 'Synthetic County', county_slug: 'synthetic-county',
    title: 'Unaccounted test assets', excerpt: 'Explicit synthetic browser finding.',
    heading: 'Basis for Qualified Opinion', fiscal_year: 'FY2025/26', page_ref: 'p.2',
    source: { document_id: 901, title: 'Synthetic report', url: 'https://example.invalid/report.pdf',
      page_url: 'https://example.invalid/report.pdf#page=2' } }] : [];
  await page.route('**/api/v1/accountability/missing-funds*', r => r.fulfill({ json: {
    basis: 'oag_finding_title', total_amount: null, total_amount_reason: 'no_amount_extracted',
    total_cases: cases.length, affected_counties: cases.length, affected_national_entities: 0,
    fiscal_years: populated ? ['FY2025/26'] : [], cases,
    reason: populated ? null : 'no_matching_findings', withheld: { count: 0, by_reason: {} },
  } }));
}

test.describe(PATH, () => {
  test('the old URL redirects here', async ({ page }) => {
    await page.goto('/accountability/missing-funds');
    await expect(page).toHaveURL(new RegExp(`${PATH}$`));
  });

  test('renders the headline stats', async ({ page }) => {
    await page.goto(PATH);
    await waitForAppReady(page);
    await expect(pageShell.h1(page)).toContainText(/Unaccounted Funds/i);
    await expect(page.getByText(/Findings listed/i)).toBeVisible();
    await expect(page.getByText(/Amount involved/i)).toBeVisible();
  });

  test('never renders a money total, and never the word "missing"', async ({ page }) => {
    await page.goto(PATH);
    await waitForAppReady(page);
    await expect(page.getByText(/Not stated here/i)).toBeVisible();
    await expect(page.getByText(/^KES\s*0$/)).toHaveCount(0);
    const body = await page.locator('main').innerText();
    expect(body).not.toMatch(/missing/i);
  });

  test('every listed finding links to a page of its report', async ({ page }) => {
    await findings(page, true);
    await page.goto(PATH);
    await waitForAppReady(page);
    await expect(page.locator('article')).toHaveCount(1, { timeout: 15_000 });
    const links = page.locator('article a[href*="#page="]');
    await expect(links).toHaveCount(1);
    await expect(links).toHaveAttribute('href', 'https://example.invalid/report.pdf#page=2');
  });

  test('the empty state explains itself and does not imply a clean bill of health', async ({ page }) => {
    await findings(page, false);
    await page.goto(PATH);
    await waitForAppReady(page);
    await expect(page.getByText(/not a finding that public money is fully accounted for/i)).toBeVisible();
    await expect(page.getByPlaceholder(/Search by county/i)).toHaveCount(0);
  });

  test('no hand-written case is named on the page', async ({ page }) => {
    // Regression fixture for F5.3: three cases shipped from a hardcoded file
    // citing no document. The file was deleted in issue #233.
    await page.goto(PATH);
    await waitForAppReady(page);
    const body = await page.locator('body').innerText();
    for (const id of ['MF_001', 'MF_002', 'MF_003']) expect(body).not.toContain(id);
  });
});
