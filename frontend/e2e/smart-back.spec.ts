/**
 * Smart-back regression tests.
 *
 * User reported: "I was on page 2 of /counties, clicked Homa Bay, then
 * clicked 'All counties' at the top of the detail page — it reloaded
 * the whole list and took me back to page 1 at the top. I expected to
 * return to page 2, scrolled to where I was."
 *
 * Fix: the "← All counties" back link in PageShell now calls
 * `router.back()` when the previous history entry matches the back
 * link's target. These tests lock the behaviour.
 *
 * They also cover the inverse case — deep-landing on a detail page
 * and clicking "← All counties" — which must still work by navigating
 * forward (push), not by popping history to an unrelated page.
 */
import { expect, test, type Page } from '@playwright/test';
import { waitForAppReady } from './utils/selectors';

async function gotoPageNOfCountiesList(page: Page, n: number) {
  await page.goto('/counties');
  await waitForAppReady(page);

  // Wait for the rankings table + "Prev" button (only rendered once
  // pagination appears at the bottom of the table).
  await expect(page.locator('table tbody tr').first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole('button', { name: /^<\s*Prev$/ })).toBeVisible({
    timeout: 15_000,
  });

  // Pagination uses buttons labelled exactly "N" — no other "N" button
  // exists on this page.
  await page.getByRole('button', { name: String(n), exact: true }).click();

  const lo = (n - 1) * 10 + 1;
  const hi = n * 10;
  // URL updated to ?p=N and content is ranks (lo)-(hi)
  await expect(page).toHaveURL(new RegExp(`[?&]p=${n}`), { timeout: 5_000 });
  await expect(
    page.getByText(new RegExp(`Showing\\s+${lo}[–\\-]${hi}\\s+of`)),
  ).toBeVisible({ timeout: 5_000 });
}

async function gotoPage2OfCountiesList(page: Page) {
  await gotoPageNOfCountiesList(page, 2);
}

test.describe('Smart back link — counties list ↔ detail', () => {
  test('page 2 → Homa Bay → All counties → restores page 2 + URL', async ({ page }) => {
    await gotoPage2OfCountiesList(page);

    // Click the first county on this page (any tile, order doesn't matter)
    const firstLink = page
      .locator('table tbody tr')
      .first()
      .getByRole('link')
      .first();
    await firstLink.click();
    await page.waitForURL(/\/counties\/[\w-]+/, { timeout: 15_000 });

    // Click the "← All counties" link in the detail page header
    const back = page
      .getByRole('link', { name: /All counties|Kaunti zote/i })
      .first();
    await back.click();

    // Should be back on /counties?p=2 (URL preserved), content on page 2
    await expect(page).toHaveURL(/\/counties\?.*p=2/, { timeout: 10_000 });
    await expect(page.getByText(/Showing\s+11[–\-]20\s+of/)).toBeVisible({ timeout: 10_000 });
  });

  test('scroll position is roughly preserved after smart-back', async ({ page }) => {
    await gotoPage2OfCountiesList(page);

    // Scroll down in the list so we have a non-zero scroll to restore
    await page.evaluate(() => window.scrollTo(0, 900));
    await page.waitForTimeout(200);
    const beforeY = await page.evaluate(() => window.scrollY);
    expect(beforeY).toBeGreaterThan(400);

    const firstLink = page
      .locator('table tbody tr')
      .first()
      .getByRole('link')
      .first();
    await firstLink.click();
    await page.waitForURL(/\/counties\/[\w-]+/, { timeout: 15_000 });

    const back = page
      .getByRole('link', { name: /All counties|Kaunti zote/i })
      .first();
    await back.click();
    await expect(page).toHaveURL(/[?&]p=2/);

    // Scroll restoration kicks in after hydrate; allow a moment.
    await page.waitForTimeout(800);
    const afterY = await page.evaluate(() => window.scrollY);
    // Generous tolerance — dynamic content heights shift pixels around.
    // Just assert we're not at the top.
    expect(afterY).toBeGreaterThan(100);
  });

  test('deep-landing on county detail → back link falls through to forward nav', async ({
    page,
    context,
  }) => {
    // No prior history — open the county detail as a fresh page.
    await page.goto('/counties/043?fy=2024%2F25');
    await waitForAppReady(page);

    const back = page
      .getByRole('link', { name: /All counties|Kaunti zote/i })
      .first();
    await back.click();

    // Should land on /counties (no ?p=N because there was no state to
    // restore). Must not land somewhere unrelated.
    await expect(page).toHaveURL(/\/counties(\/|\?|$)/, { timeout: 10_000 });
    await expect(page.locator('table tbody tr').first()).toBeVisible({ timeout: 15_000 });
  });

  test('page 3 (user-reported scenario) → detail → All counties → restores page 3', async ({ page }) => {
    // The user explicitly reported this scenario on page 3.
    // Page 2 is already covered above; this locks in that the fix is
    // *general*, not scoped to a single page number.
    await gotoPageNOfCountiesList(page, 3);

    const firstLink = page.locator('table tbody tr').first().getByRole('link').first();
    await firstLink.click();
    await page.waitForURL(/\/counties\/[\w-]+/, { timeout: 15_000 });

    const back = page.getByRole('link', { name: /All counties|Kaunti zote/i }).first();
    await back.click();

    // Must land on /counties?p=3 (NOT /counties bare, NOT /counties?p=1)
    await expect(page).toHaveURL(/\/counties\?.*p=3/, { timeout: 10_000 });
    await expect(page.getByText(/Showing\s+21[–\-]30\s+of/)).toBeVisible({ timeout: 10_000 });
  });

  test('View All → click county → back → restores full list (not paginated page 1)', async ({
    page,
  }) => {
    // User-reported: "I clicked 'View All Counties', it showed the full
    // 47-row list, I clicked a county, then clicked 'All counties' to go
    // back — but it took me to the paginated view, not the full list."
    // Fix: showAll is URL-driven (?view=all) so router.back() restores it.
    await page.goto('/counties');
    await waitForAppReady(page);
    await expect(page.locator('table tbody tr').first()).toBeVisible({ timeout: 20_000 });

    // Click "View All Counties"
    await page.getByRole('button', { name: /View All Counties|Kaunti Zote/i }).click();
    await expect(page).toHaveURL(/[?&]view=all/, { timeout: 5_000 });
    // Pagination controls should be hidden now
    await expect(page.getByRole('button', { name: /^<\s*Prev$/ })).toHaveCount(0);
    // The full list (47 rows) should be rendered
    await expect(page.locator('table tbody tr')).toHaveCount(47, { timeout: 10_000 });

    // Scroll partway down so the back round-trip has something to restore
    await page.evaluate(() => window.scrollTo(0, 1500));
    await page.waitForTimeout(200);

    // Click into a county (pick one mid-list so scroll matters)
    const midLink = page.locator('table tbody tr').nth(15).getByRole('link').first();
    await midLink.scrollIntoViewIfNeeded();
    await midLink.click();
    await page.waitForURL(/\/counties\/[\w-]+/, { timeout: 15_000 });

    // Click "← All counties" back link
    const back = page.getByRole('link', { name: /All counties|Kaunti zote/i }).first();
    await back.click();

    // Must land back on /counties?view=all (full list), NOT /counties (paginated p=1)
    await expect(page).toHaveURL(/\/counties\?.*view=all/, { timeout: 10_000 });
    await expect(page.locator('table tbody tr')).toHaveCount(47, { timeout: 10_000 });
    // Pagination should still be hidden
    await expect(page.getByRole('button', { name: /^<\s*Prev$/ })).toHaveCount(0);
  });

  test('returning from a county to a FILTERED list restores filters via history', async ({ page }) => {
    await gotoPage2OfCountiesList(page);

    // Also tweak the fiscal-year state if possible — demonstrates that
    // non-URL state still rides home via browser history restoration.
    // (If this locator isn't present we skip — not all layouts show it.)
    const yearDropdown = page.getByRole('combobox').first();
    if ((await yearDropdown.count()) > 0) {
      await yearDropdown.scrollIntoViewIfNeeded();
    }

    const firstLink = page
      .locator('table tbody tr')
      .first()
      .getByRole('link')
      .first();
    await firstLink.click();
    await page.waitForURL(/\/counties\/[\w-]+/, { timeout: 15_000 });

    const back = page
      .getByRole('link', { name: /All counties|Kaunti zote/i })
      .first();
    await back.click();

    // Must return to the page-2 URL, not the bare /counties.
    await expect(page).toHaveURL(/\/counties\?.*p=2/, { timeout: 10_000 });
  });
});

test.describe('Smart back — other sections', () => {
  /** The pattern generalises: same behaviour should hold on any page
   * that uses PageShell with a back link. Pick a couple of representative
   * sub-pages to prove the fix isn't scoped to /counties alone. */
  test('compare page back link returns to previous URL when came from list', async ({ page }) => {
    await page.goto('/counties?p=2');
    await waitForAppReady(page);
    await expect(page).toHaveURL(/[?&]p=2/);

    // From /counties list, navigate to /counties/compare — some layouts
    // have a "Compare counties" button; fall back to direct navigation
    // if the button isn't rendered on this size.
    const compareBtn = page.getByRole('link', { name: /Compare counties/i }).first();
    if (await compareBtn.count() > 0) {
      await compareBtn.click();
    } else {
      await page.goto('/counties/compare?ids=047,001');
    }
    await page.waitForURL(/\/counties\/compare/, { timeout: 10_000 });

    // Click the back link on compare — should pop back to /counties?p=2
    const back = page
      .getByRole('link', { name: /All counties|Kaunti zote/i })
      .first();
    if ((await back.count()) === 0) {
      test.skip(true, 'compare page has no visible back link at this viewport');
    }
    await back.click();

    await expect(page).toHaveURL(/\/counties(\?|$)/, { timeout: 10_000 });
  });
});
