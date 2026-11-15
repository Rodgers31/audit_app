import { expect, test, type Page } from '@playwright/test';

const publication = (source: string, last_updated: string, status = 'fresh') => ({
  source, label: source, status, last_updated,
  covers_through: 'FY2025/26 9M', update_frequency: 'Quarterly',
});
const cob = publication('COB', '2025-10-10');
const treasury = publication('Treasury', '2025-10-15');
const freshnessURL = '**/api/v1/data/freshness';
const freshnessVerdict = /^(?:Up to date|May be stale|Out of date|Freshness unknown)(?: ·|$)/;

async function openBudget(page: Page, sources: readonly (ReturnType<typeof publication> & { last_checked?: string })[]) {
  await page.route(freshnessURL, route => route.fulfill({ json: { sources } }));
  const response = page.waitForResponse(freshnessURL);
  await page.goto('/budget');
  expect((await response).ok()).toBe(true);
  await expect(page.getByRole('heading', { name: "Kenya's Budget & Spending", exact: true })).toBeVisible();
}

for (const [name, sources, label] of [
  ['complete', [cob, treasury], 'Up to date'],
  ['stale', [cob, { ...treasury, status: 'stale' }], 'May be stale'],
] as const) {
  test(`budget freshness is ${name}`, async ({ page }) => {
    await openBudget(page, sources);
    const verdict = page.getByText(label, { exact: true });
    await expect(verdict).toBeVisible();
    await expect(verdict.locator('..')).toHaveText(`${label} · Data as of 10 Oct 2025 · COB / Treasury`);
    await expect(page.getByText(freshnessVerdict)).toHaveCount(1);
  });
}

test('partial publisher coverage shows only the verified check date', async ({ page }) => {
  await openBudget(page, [{ ...cob, last_checked: '2025-10-20' }]);
  await expect(page.getByText('Checked 20 Oct 2025 · COB', { exact: true })).toBeVisible();
  await expect(page.getByText(freshnessVerdict)).toHaveCount(0);
  await expect(page.getByText(/Data as of .* · COB/)).toHaveCount(0);
});

test('unavailable freshness evidence leaves the verdict absent', async ({ page }) => {
  await openBudget(page, []);
  await expect(page.getByText(freshnessVerdict)).toHaveCount(0);
  await expect(page.getByText(/^Checked .* · (?:COB|Treasury)/)).toHaveCount(0);
});

test('no JavaScript readers receive the budget without a freshness verdict', async ({ browser, baseURL }) => {
  const context = await browser.newContext({ baseURL, javaScriptEnabled: false });
  const page = await context.newPage();
  try {
    await page.goto('/budget');
    await expect(page.getByRole('heading', { name: "Kenya's Budget & Spending", exact: true })).toBeVisible();
    await expect(page.getByText(freshnessVerdict)).toHaveCount(0);
    await expect(page.getByText('Checking data freshness…', { exact: true })).toHaveCount(0);
  } finally {
    await context.close();
  }
});
