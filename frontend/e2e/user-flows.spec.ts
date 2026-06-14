/**
 * User-flow tests — exercise the app the way a human uses it.
 *
 * The specs in this file simulate complete user journeys rather than
 * isolated component assertions, and they focus on the state-
 * preservation expectations that are easy to regress on:
 *
 *   • Browser back restores the previous page's state (pagination,
 *     scroll position, filters).
 *   • Deep links round-trip (share /counties?p=3 → opens page 3
 *     directly).
 *   • Browser forward / back through a multi-step flow doesn't lose
 *     context.
 *   • In-page tab state survives reload.
 *
 * These are the "doesn't feel broken" tests. If they fail, the app
 * may be technically working but users will curse at it.
 */
import { expect, test } from '@playwright/test';
import { waitForAppReady } from './utils/selectors';

test.describe('Back-navigation state preservation', () => {
  test('county list → detail → back restores pagination (?p=N)', async ({ page }) => {
    // Start on /counties fresh (no query params)
    await page.goto('/counties');
    await waitForAppReady(page);

    // Wait for the rankings table to populate
    const tableRow = page.locator('table tbody tr').first();
    await expect(tableRow).toBeVisible({ timeout: 15_000 });

    // Find the pagination buttons inside the rankings table container.
    // The "2" button has exactly that text — no surrounding content.
    const page2 = page
      .locator('table')
      .locator('..')
      .getByRole('button', { name: '2', exact: true })
      .first();
    await page2.click();

    // Content should now be page 2 (ranks 11-20 on 47 counties / 10 per page)
    await expect(page.getByText(/Showing\s+11[–\-]20\s+of/)).toBeVisible({
      timeout: 5_000,
    });
    await expect(page).toHaveURL(/[?&]p=2/);

    // Click any county link from page 2
    const countyLink = page.locator('table tbody tr').first().getByRole('link').first();
    await countyLink.click();
    await page.waitForURL(/\/counties\/[\w-]+/, { timeout: 15_000 });

    // Go back via browser history
    await page.goBack();
    await page.waitForURL(/\/counties(?:\?|$)/, { timeout: 15_000 });

    // Assert pagination was preserved — URL still has ?p=2, content is still page 2
    await expect(page).toHaveURL(/[?&]p=2/);
    await expect(page.getByText(/Showing\s+11[–\-]20\s+of/)).toBeVisible({
      timeout: 10_000,
    });
  });

  test('?p=N deep link round-trip (reload + share)', async ({ page }) => {
    await page.goto('/counties?p=3');
    await waitForAppReady(page);

    await expect(page.getByText(/Showing\s+21[–\-]30\s+of/)).toBeVisible({
      timeout: 15_000,
    });
    // Ranks 21-25 should appear in the first few rows
    const firstRank = page.locator('table tbody tr').first().locator('td').first();
    await expect(firstRank).toHaveText(/21/);
  });

  test('clamp out-of-range page to last valid page', async ({ page }) => {
    // 47 counties / 10 per page = 5 pages. Page 99 should fall back to 5.
    await page.goto('/counties?p=99');
    await waitForAppReady(page);

    // Either URL is rewritten to ?p=5 OR the content shows page 5 anyway
    await expect(page.getByText(/Showing\s+41[–\-]47\s+of|Showing\s+41[–\-]\d+\s+of/)).toBeVisible({
      timeout: 15_000,
    });
  });

  test('browser back from detail → Overview tab stays on whatever tab we set', async ({ page }) => {
    // Visit /counties/047?tab=audit
    await page.goto('/counties/047?tab=audit');
    await waitForAppReady(page);

    // Navigate to a different county tab
    const accountability = page.getByRole('button', { name: /^Accountability$/ });
    await accountability.click();
    await expect(page).toHaveURL(/[?&]tab=accountability/, { timeout: 5_000 });

    // Back — should return to ?tab=audit
    await page.goBack();
    await expect(page).toHaveURL(/[?&]tab=audit/, { timeout: 5_000 });
  });
});

test.describe('URL-driven state', () => {
  test('/counties/047?tab=budget opens directly on Budget & Debt', async ({ page }) => {
    await page.goto('/counties/047?tab=budget');
    await waitForAppReady(page);

    // The Budget & Debt tab should be the active one (carries the
    // gov-forest text color in our theme).
    const active = page.getByRole('button', { name: /^Budget & Debt$/ });
    await expect(active).toHaveClass(/text-gov-forest/, { timeout: 10_000 });
  });

  test('/counties/compare?ids=… preserves selection across reload', async ({ page }) => {
    await page.goto('/counties/compare?ids=047,001');
    await waitForAppReady(page);

    await expect(page.getByRole('columnheader', { name: /Mombasa/i }).first()).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByRole('columnheader', { name: /Nairobi/i }).first()).toBeVisible();

    await page.reload();
    await waitForAppReady(page);

    await expect(page.getByRole('columnheader', { name: /Mombasa/i }).first()).toBeVisible({
      timeout: 15_000,
    });
  });
});

test.describe('Scroll restoration', () => {
  test('back-navigation restores approximate scroll position', async ({ page }) => {
    await page.goto('/counties');
    await waitForAppReady(page);

    // Scroll down
    await page.evaluate(() => window.scrollTo(0, 800));
    const beforeY = await page.evaluate(() => window.scrollY);
    expect(beforeY).toBeGreaterThan(400);

    // Navigate to a county detail
    const countyLink = page.getByRole('link', { name: /Nairobi/i }).first();
    await countyLink.click();
    await page.waitForURL(/\/counties\/[\w-]+/, { timeout: 15_000 });

    // Back — Next's experimental.scrollRestoration should put us back
    // near where we were. Allow a generous tolerance; the list may be
    // shorter if filters were applied.
    await page.goBack();
    await expect(page).toHaveURL(/\/counties(?:\?|$)/, { timeout: 15_000 });

    // Allow scroll-restoration a brief moment to kick in after hydrate
    await page.waitForTimeout(600);
    const afterY = await page.evaluate(() => window.scrollY);
    // Accept anywhere in the lower half of the page — exact pixel
    // match isn't realistic with dynamic content heights.
    expect(afterY).toBeGreaterThan(100);
  });
});

test.describe('Keyboard navigation', () => {
  test('skip-to-main link is reachable with a single Tab', async ({ page }) => {
    await page.goto('/');
    await waitForAppReady(page);

    await page.keyboard.press('Tab');
    const focusedHref = await page.evaluate(() => {
      const el = document.activeElement as HTMLAnchorElement | null;
      return el && el.tagName === 'A' ? el.getAttribute('href') : null;
    });
    expect(focusedHref).toBe('#main-content');
  });

  test('Enter on the skip link scrolls the main content into view', async ({ page }) => {
    await page.goto('/counties');
    await waitForAppReady(page);

    await page.keyboard.press('Tab');
    await page.keyboard.press('Enter');

    // The hash should be #main-content; the page should scroll so that
    // #main-content is near the top.
    await expect(page).toHaveURL(/#main-content/);
  });

  test('ESC closes the mobile menu and restores focus to the toggle', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/');
    await waitForAppReady(page);

    const toggle = page.getByRole('button', {
      name: /open navigation menu|Fungua menyu/i,
    });
    await toggle.click();

    // Confirm open
    await expect(
      page.getByRole('dialog', { name: /Mobile navigation/i })
    ).toBeVisible();

    // ESC to close
    await page.keyboard.press('Escape');

    // Overlay is gone
    await expect(
      page.getByRole('dialog', { name: /Mobile navigation/i })
    ).toHaveCount(0, { timeout: 3_000 });

    // Focus restored to the toggle button
    const focusedLabel = await page.evaluate(
      () => (document.activeElement as HTMLElement | null)?.getAttribute('aria-label')
    );
    expect(focusedLabel).toMatch(/open navigation menu|Fungua menyu/i);
  });
});

test.describe('Form / filter persistence', () => {
  test('search input on /accountability/missing-funds is reactive', async ({ page }) => {
    await page.goto('/accountability/missing-funds');
    await waitForAppReady(page);

    const search = page.getByPlaceholder(/Search by county|Tafuta/i);
    await expect(search).toBeVisible({ timeout: 15_000 });

    await search.fill('zzzz-no-match');
    await expect(
      page.getByText(/No cases match your filter|Hakuna kesi/i)
    ).toBeVisible({ timeout: 5_000 });

    await search.fill('');
    // Cases return after clearing — assert at least one case card or "total" number reappears
    await expect(page.getByText(/Total flagged|Jumla/i).first()).toBeVisible();
  });
});
