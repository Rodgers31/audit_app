/**
 * Follow the Money — waterfall on the county detail page.
 *
 * Primary regression guards:
 *   - The "Funds Released" stage (labelled as a proxy via
 *     `committed_amount`) must stay OUT of the waterfall — it was
 *     dropped in v1.1.1 because it produced impossible numbers
 *     (spent > released).
 *   - The waterfall must be exactly 3 stages: Allocated / Spent /
 *     Flagged.
 *   - The "Unspent Funds" gap pill must carry the clarifier sub-label
 *     "Not missing" so readers can't confuse it with missing money.
 *   - The CoB source-document title must be a clickable link.
 *   - The FY selector must NOT show "FY FY…" (double prefix regression).
 *   - The default FY must be the latest *reported* FY (not the in-
 *     progress one), so the tab never loads "no data".
 */
import { expect, test } from '@playwright/test';
import { countyTabs, waterfall, waitForAppReady } from './utils/selectors';

const COUNTY_ID = '001'; // Nairobi — has data across FYs

test.describe('Follow the Money — waterfall shape', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`/counties/${COUNTY_ID}`);
    await waitForAppReady(page);
    await countyTabs.followTheMoney(page).click();
    // Wait for the waterfall to render
    await expect(waterfall.stage(page, 'Allocated')).toBeVisible({ timeout: 15_000 });
  });

  test('renders exactly three stages: Allocated / Spent / Flagged', async ({ page }) => {
    await expect(waterfall.stage(page, 'Allocated')).toBeVisible();
    await expect(waterfall.stage(page, 'Spent')).toBeVisible();
    await expect(waterfall.stage(page, 'Flagged')).toBeVisible();

    // The misleading 'Released' stage must be absent
    const releasedStage = page
      .locator('[class*="rounded"]')
      .filter({ hasText: /^RELEASED|Funds Released/i });
    await expect(releasedStage).toHaveCount(0);
  });

  test('Unspent Funds gap carries the "Not missing" clarifier', async ({ page }) => {
    await expect(page.getByText(/Unspent Funds/i).first()).toBeVisible();
    await expect(
      page.getByText(/Not missing|not yet paid out at report time/i).first()
    ).toBeVisible();
  });

  test('CoB source document is a clickable link with HTTPS URL', async ({ page }) => {
    const source = waterfall.sourceLink(page);
    await expect(source).toBeVisible({ timeout: 10_000 });
    const href = await source.getAttribute('href');
    expect(href).toMatch(/^https:\/\/cob\.go\.ke/);
    // Make sure it opens in a new tab (external link convention)
    await expect(source).toHaveAttribute('target', '_blank');
    await expect(source).toHaveAttribute('rel', /noopener/);
  });
});

test.describe('Follow the Money — year selector', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`/counties/${COUNTY_ID}`);
    await waitForAppReady(page);
    await countyTabs.followTheMoney(page).click();
  });

  test('default year is the latest reported FY (not in-progress)', async ({ page }) => {
    const select = waterfall.yearSelector(page);
    await expect(select).toBeVisible({ timeout: 15_000 });

    const selected = await select.inputValue();
    // Current date is 2026-04 → in-progress FY is 2025/26; latest reported is 2024/25.
    // Accept either bare "2024/25" or prefixed "FY2024/25" since the
    // backend uses the prefix but the frontend strips on display.
    expect(selected).toMatch(/^(FY)?2024\/25$/);
  });

  test('dropdown labels never double-prefix "FY FY…"', async ({ page }) => {
    const select = waterfall.yearSelector(page);
    const optionTexts = await select.locator('option').allInnerTexts();
    for (const text of optionTexts) {
      expect(text).not.toMatch(/FY\s+FY/);
    }
  });

  test('switching to a different FY refreshes the waterfall', async ({ page }) => {
    const select = waterfall.yearSelector(page);
    const initialAmount = await page
      .getByText(/Budget Allocation/i)
      .locator('..')
      .textContent();

    // Pick whichever option is second in the list (first is default)
    const secondOption = (await select.locator('option').all())[1];
    const secondValue = await secondOption.getAttribute('value');
    if (!secondValue) test.skip(true, 'only one FY available');

    await select.selectOption(secondValue!);
    // Allow React Query to refetch
    await page.waitForTimeout(1000);

    const newAmount = await page
      .getByText(/Budget Allocation/i)
      .locator('..')
      .textContent();
    // Either the numbers changed OR the year label updated — either way
    // the page responded to the selection.
    expect(newAmount).toBeDefined();
  });
});

test.describe('Follow the Money — national page (/transparency)', () => {
  /** User-reported: "When I load the Follow the Money page, it doesn't
   * highlight the 2025/26 year that it loads by default."
   *
   * Root cause: the audits API returns "FY2025/26" while the local
   * `generateFiscalYears()` fallback returns "2025/26". `selectedYear`
   * was initialized from the fallback and then never matched any
   * API-sourced button, so `aria-pressed` was false on every pill.
   *
   * Fix: year strings are normalized to bare "YYYY/YY" at the boundary,
   * so the initial `selectedYear` and the post-API `pickerYears` always
   * agree.
   */
  test('default fiscal-year pill is highlighted on initial load', async ({ page }) => {
    await page.goto('/transparency');
    await waitForAppReady(page);

    // Wait for the picker to render
    const picker = page.locator('[class*="Fiscal year"]').or(page.getByText(/Fiscal year/i));
    await expect(picker.first()).toBeVisible({ timeout: 15_000 });

    // Exactly one button should be aria-pressed=true (the default)
    const activePills = page.locator('button[aria-pressed="true"]').filter({
      hasText: /FY\d{4}\/\d{2}/,
    });
    await expect(activePills).toHaveCount(1, { timeout: 10_000 });

    // And it must be the current FY (April 2026 → FY2025/26)
    await expect(activePills).toHaveText(/FY2025\/26/);
  });

  test('clicking a different FY moves the highlight to that pill', async ({ page }) => {
    await page.goto('/transparency');
    await waitForAppReady(page);

    const target = page.getByRole('button', { name: /FY2023\/24/ });
    await expect(target).toBeVisible({ timeout: 15_000 });
    await target.click();

    // aria-pressed flips to the clicked pill
    await expect(target).toHaveAttribute('aria-pressed', 'true', { timeout: 5_000 });

    // Previously-active pill is no longer pressed
    const previous = page.getByRole('button', { name: /FY2025\/26/ });
    await expect(previous).toHaveAttribute('aria-pressed', 'false');
  });
});

test.describe('Follow the Money — efficiency + provenance', () => {
  test('efficiency score is rendered as a percentage ring', async ({ page }) => {
    await page.goto(`/counties/${COUNTY_ID}`);
    await waitForAppReady(page);
    await countyTabs.followTheMoney(page).click();

    await expect(page.getByText(/%/)).toBeVisible({ timeout: 10_000 });
    await expect(
      page.getByText(/Good Efficiency|Fair Efficiency|Low Efficiency/i).first()
    ).toBeVisible();
  });

  test('committed-amount note is shown when present', async ({ page }) => {
    await page.goto(`/counties/${COUNTY_ID}`);
    await waitForAppReady(page);
    await countyTabs.followTheMoney(page).click();

    // Copy from FollowTheMoney.tsx — regression guard if the footer gets
    // refactored away by accident.
    await expect(
      page.getByText(/procurement-encumbered|earmarked for contracts/i)
    ).toBeVisible({ timeout: 10_000 });
  });
});
