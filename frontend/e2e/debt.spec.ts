import { expect, test } from '@playwright/test';
import { registerApiMocks } from './utils/mockApi';

test.beforeEach(async ({ page }) => { await registerApiMocks(page); });

test('national debt page shows key stats and charts', async ({ page }) => {
  await page.goto('/debt');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText("Kenya's National Debt");
  const ratio = page.getByText('Debt-to-GDP', { exact: true }).locator('..');
  await expect(ratio).toContainText('60.0%');
  await expect(ratio).toContainText('Synthetic browser fixture');
  await expect(ratio).toContainText('Observation: 2025');
  await expect(page.getByText('Not assessed', { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'The cost of debt over time' })).toBeVisible();
  await expect(page.locator('.recharts-wrapper').first()).toBeVisible();
});

test('"Where every KES 100" card uses the synthetic fiscal-summary ratio (50, tax + non-tax revenue)', async ({ page }) => {
  await page.goto('/debt');
  await expect(page.getByRole('heading', { name: /Where every KES 100 of revenue goes/i })).toBeVisible();
  await expect(page.getByTestId('debt-headline-kes')).toHaveText('50');
  await expect(page.getByText(/Debt service takes about/i)).toBeVisible();
  await expect(page.getByText(/Spending per KES 100 of revenue: 150\.0/i)).toBeVisible();
  await expect(page.getByText(/The 50\.0 above 100 is financed by A-i-A \(20\.0\), grants \(5\.0\), net borrowing \(25\.0\)/i)).toBeVisible();
});

test('debt page exposes a methodology disclosure with the total-debt-service calculation', async ({ page }) => {
  await page.goto('/debt');
  const summary = page.getByText('How this is calculated', { exact: true });
  await summary.click();
  const disclosure = summary.locator('..');
  await expect(disclosure).toContainText('50');
  await expect(disclosure).toContainText(/interest|principal/i);
  await expect(disclosure).toContainText(/Different official debt-service measures/i);
});

test('debt page does not undermine the headline with discouraging copy', async ({ page }) => {
  await page.goto('/debt');
  // Establish that the card actually rendered before testing absent wording.
  await expect(page.getByTestId('debt-headline-kes')).toHaveText('50');
  for (const text of [/actual number is higher/i, /real number is higher/i, /this number is incomplete/i]) {
    await expect(page.getByText(text)).toHaveCount(0);
  }
});

test('debt page source line names the ratio inputs explicitly', async ({ page }) => {
  await page.goto('/debt');
  await expect(page.getByText(/Uses tax & non-tax revenue; debt figure includes total debt service/i)).toContainText('(interest + principal redemptions)');
  // This fixture has no APDMR source metadata; do not invent a Treasury citation.
  await expect(page.getByText(/The source document for FY 2025\/26's debt-service figure is not recorded/i)).toBeVisible();
});
