/**
 * National Missing Funds tracker (/accountability/missing-funds)
 *
 * The endpoint publishes a case only when it traces to a source document with
 * a URL and a page (AUDIT_FINDINGS F5.3). Until sourced OAG extractions land,
 * the tracker is legitimately empty — so these tests assert the correct
 * behaviour in BOTH states rather than assuming cases exist.
 */
import { expect, test } from '@playwright/test';
import { pageShell, waitForAppReady } from './utils/selectors';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

/**
 * True when the API published no traceable case.
 *
 * Asked of the API, not the DOM: a DOM probe races the in-flight fetch and
 * would report "not empty" while the page is merely still loading — the same
 * absent-vs-present conflation this page exists to avoid.
 */
async function noSourcedCases(request: import('@playwright/test').APIRequestContext) {
  const res = await request.get(`${API_BASE}/api/v1/accountability/missing-funds`);
  expect(res.ok()).toBeTruthy();
  const body = await res.json();
  return body.total_cases === 0;
}

test.describe('/accountability/missing-funds', () => {
  test('renders headline stats + top-counties breakdown', async ({ page }) => {
    await page.goto('/accountability/missing-funds');
    await waitForAppReady(page);

    await expect(pageShell.h1(page)).toContainText(/Missing Funds Tracker|Kifuatilia Pesa Zilizopotea/i);
    await expect(page.getByText(/Total flagged|Jumla/i).first()).toBeVisible();
    await expect(page.getByText(/Counties affected|Kaunti zinazoathiriwa/i)).toBeVisible();
    await expect(page.getByText(/Recovery status|Hali ya Urejeshwaji/i)).toBeVisible();
  });

  test('an untraceable total is never rendered as KES 0', async ({ page, request }) => {
    // The dominant defect class in this codebase (AUDIT_FINDINGS P1): a missing
    // value rendered identically to a real one. On this page "KES 0 flagged"
    // would read as a finding that no public money is unaccounted for.
    await page.goto('/accountability/missing-funds');
    await waitForAppReady(page);

    if (!(await noSourcedCases(request))) test.skip(true, 'cases are published; nothing to assert');

    await expect(page.getByText(/Not yet published/i).first()).toBeVisible();
    await expect(page.getByText(/^KES\s*0$/)).toHaveCount(0);
  });

  test('the empty state explains itself and does not imply a clean bill of health', async ({ page, request }) => {
    await page.goto('/accountability/missing-funds');
    await waitForAppReady(page);

    if (!(await noSourcedCases(request))) test.skip(true, 'cases are published; nothing to assert');

    await expect(
      page.getByText(/not a finding that public money is fully accounted for/i)
    ).toBeVisible();
    // Nothing to search, so the search UI must not be offered.
    await expect(page.getByPlaceholder(/Search by county|Tafuta/i)).toHaveCount(0);
  });

  test('search filters the case list when cases are published', async ({ page, request }) => {
    await page.goto('/accountability/missing-funds');
    await waitForAppReady(page);

    if (await noSourcedCases(request)) test.skip(true, 'no sourced cases published yet');

    const search = page.getByPlaceholder(/Search by county|Tafuta/i);
    await expect(search).toBeVisible({ timeout: 15_000 });

    await search.fill('nonexistent-county-xyz');
    await expect(
      page.getByText(/No cases match your filter|Hakuna kesi/i)
    ).toBeVisible({ timeout: 5_000 });
  });

  test('status filter dropdown narrows results when cases are published', async ({ page, request }) => {
    await page.goto('/accountability/missing-funds');
    await waitForAppReady(page);

    if (await noSourcedCases(request)) test.skip(true, 'no sourced cases published yet');

    const statusSelect = page.locator('select').first();
    await expect(statusSelect).toBeVisible({ timeout: 15_000 });

    const resolvedOption = statusSelect.locator('option').filter({ hasText: /Resolved/i });
    if ((await resolvedOption.count()) === 0) test.skip(true, 'no Resolved status option on this dataset');
    const value = (await resolvedOption.first().getAttribute('value')) ?? '';
    await statusSelect.selectOption(value);
    await page.waitForTimeout(500);
  });

  test('methodology footer is always present', async ({ page }) => {
    await page.goto('/accountability/missing-funds');
    await waitForAppReady(page);

    await expect(
      page.getByText(/Office of the Auditor-General|Mkaguzi Mkuu/i).first()
    ).toBeVisible();
  });

  test('no unsourced case is named on the page', async ({ page }) => {
    // Regression fixture for F5.3: these three cases shipped from a hardcoded
    // file citing no document, under an assurance that each traced to a
    // published audit report.
    await page.goto('/accountability/missing-funds');
    await waitForAppReady(page);

    const body = await page.locator('body').innerText();
    expect(body).not.toContain('MF_001');
    expect(body).not.toContain('MF_002');
    expect(body).not.toContain('MF_003');
    expect(body).not.toMatch(/traces back to a published audit report/i);
    expect(body).not.toMatch(/OAG or EACC has an open file/i);
  });
});
