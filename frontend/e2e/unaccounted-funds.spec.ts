/**
 * Unaccounted Funds (/accountability/unaccounted-funds, formerly /missing-funds)
 *
 * Lists findings the Auditor-General's report itself heads "Unaccounted …" or
 * "Loss of Funds", each linked to its page (issue #233). It publishes no money
 * total in any state. These tests assert the correct behaviour whether or not
 * the API currently lists any finding.
 */
import { expect, test } from '@playwright/test';
import { pageShell, waitForAppReady } from './utils/selectors';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const PATH = '/accountability/unaccounted-funds';

/** Asked of the API, not the DOM: a DOM probe races the in-flight fetch. */
async function listedCount(request: import('@playwright/test').APIRequestContext) {
  const res = await request.get(`${API_BASE}/api/v1/accountability/missing-funds`);
  expect(res.ok()).toBeTruthy();
  const body = await res.json();
  expect(body.total_amount).toBeNull();
  return body.total_cases as number;
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

  test('every listed finding links to a page of its report', async ({ page, request }) => {
    await page.goto(PATH);
    await waitForAppReady(page);
    const n = await listedCount(request);
    if (n === 0) test.skip(true, 'no finding listed on this dataset');
    await expect(page.locator('article')).toHaveCount(n, { timeout: 15_000 });
    const links = page.locator('article a[href*="#page="]');
    expect(await links.count()).toBeGreaterThan(0);
  });

  test('the empty state explains itself and does not imply a clean bill of health', async ({ page, request }) => {
    await page.goto(PATH);
    await waitForAppReady(page);
    if ((await listedCount(request)) > 0) test.skip(true, 'findings are listed; nothing to assert');
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
