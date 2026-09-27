import { expect, test } from '@playwright/test';
import { registerApiMocks } from './utils/mockApi';

test.beforeEach(async ({ page }) => {
  await registerApiMocks(page);
});

test('national debt page shows key stats and charts', async ({ page }) => {
  await page.goto('/debt');

  await expect(page.getByText("Kenya's National Debt Explained")).toBeVisible();

  // Key stats - use role-based selectors to avoid strict mode violations
  await expect(page.getByRole('heading', { name: 'Total Debt' })).toBeVisible();
  await expect(page.getByRole('heading', { name: /Per Citizen/i })).toBeVisible();
  await expect(page.getByRole('heading', { name: /Debt-to-GDP/i })).toBeVisible();
  await expect(page.getByRole('heading', { name: /Risk Level/i })).toBeVisible();

  // Charts sections present
  await expect(page.getByRole('heading', { name: /Debt Growth Over Time/i })).toBeVisible();
  await expect(page.getByRole('heading', { name: /Domestic vs External Debt/i })).toBeVisible();

  // Top loans section present
  await expect(page.getByRole('heading', { name: /Top 5 Largest Loans/i })).toBeVisible();
});

test('"Where every KES 100" card uses the fiscal-summary ratio (about KES 78, tax + non-tax revenue)', async ({
  page,
}) => {
  await page.goto('/debt');

  await expect(
    page.getByRole('heading', { name: /Where every KES 100 of revenue goes/i }),
  ).toBeVisible();

  // Headline number: FY 2026/27 2315.9 / 2985.7 × 100 = 77.6 → rounds to 78
  await expect(page.getByTestId('debt-headline-kes')).toHaveText('78');

  // Eyebrow includes the "about" honesty hedge
  await expect(page.getByText(/Debt service takes about/i)).toBeVisible();

  // Wording explicitly says "tax & non-tax revenue"
  await expect(
    page.getByText(/tax & non-tax revenue/i),
  ).toBeVisible();

  // The breakdown is one fiscal-framework column per KES 100 of the same
  // revenue (issue #237): 4785.2 / 2985.7 × 100 = 160, and the part above
  // 100 is shown with what financed it rather than as a computed residual.
  await expect(
    page.getByText(/Spending per KES 100 of revenue: 160\.3/i),
  ).toBeVisible();
  // 21.6 + 1.5 + 37.2 = 60.3 = 160.3 - 100: the parts add up on the page.
  await expect(
    page.getByText(/The 60\.3 above 100 is financed by A-i-A \(21\.6\), grants \(1\.5\), net borrowing \(37\.2\)/i),
  ).toBeVisible();
});

test('debt page exposes a methodology disclosure with the total-debt-service calculation', async ({
  page,
}) => {
  await page.goto('/debt');

  // The disclosure is present and clickable
  const summary = page.getByText('How this is calculated', { exact: true });
  await expect(summary).toBeVisible();
  await summary.click();

  // The calculation text appears once expanded
  await expect(
    page.getByText(/total debt service of about KSh/i),
  ).toBeVisible();
  await expect(
    page.getByText(/tax & non-tax revenue of about KSh/i),
  ).toBeVisible();

  // The transparency caveat is present
  await expect(
    page.getByText(/Different official debt-service measures/i),
  ).toBeVisible();
});

test('debt page does not undermine the headline with discouraging copy', async ({
  page,
}) => {
  await page.goto('/debt');
  await expect(page.getByText(/actual number is higher/i)).toHaveCount(0);
  await expect(page.getByText(/real number is higher/i)).toHaveCount(0);
  await expect(page.getByText(/this number is incomplete/i)).toHaveCount(0);
});

test('debt page source line names the ratio inputs explicitly', async ({
  page,
}) => {
  await page.goto('/debt');
  await expect(
    page.getByText(/National Treasury fiscal summary/i),
  ).toBeVisible();
  await expect(
    page.getByText(/tax & non-tax revenue/i),
  ).toBeVisible();
  await expect(
    page.getByText(
      /total debt service \(interest \+ principal redemptions\)/i,
    ),
  ).toBeVisible();
});
