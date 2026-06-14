/**
 * Responsive / mobile-viewport sanity checks.
 *
 * The app is desktop-first but common mobile breakpoints shouldn't
 * break the primary flows. Tests use iPhone-12 (390×844) and iPad-mini
 * (768×1024) viewports to cover small + medium screens.
 */
import { expect, test, devices } from '@playwright/test';
import { nav, waitForAppReady } from './utils/selectors';

const MOBILE = { ...devices['iPhone 12'], viewport: { width: 390, height: 844 } };
const TABLET = { ...devices['iPad Mini'], viewport: { width: 768, height: 1024 } };

test.describe('Mobile — 390×844', () => {
  test.use(MOBILE);

  test('home hero and nav render without horizontal scroll', async ({ page }) => {
    await page.goto('/');
    await waitForAppReady(page);

    // No horizontal scrollbar (width of html === viewport width).
    const scrollable = await page.evaluate(() => {
      return document.documentElement.scrollWidth > document.documentElement.clientWidth;
    });
    expect(scrollable).toBe(false);

    // Hamburger should be visible; desktop nav should not steal all screen width.
    await expect(nav.mobileMenuToggle(page)).toBeVisible();
  });

  test('/counties list is usable on mobile', async ({ page }) => {
    await page.goto('/counties');
    await waitForAppReady(page);

    // At least one county tile visible
    await expect(page.getByText(/Nairobi|Mombasa/).first()).toBeVisible({ timeout: 15_000 });

    // No horizontal overflow
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth
    );
    expect(overflow).toBe(false);
  });

  test('county detail tabs are reachable (horizontal scroll)', async ({ page }) => {
    await page.goto('/counties/001');
    await waitForAppReady(page);

    // Tabs container has `overflow-x-auto` at mobile width
    await expect(page.getByRole('button', { name: /Overview|Muhtasari/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /Projects|Miradi/i })).toBeVisible();
  });
});

test.describe('Tablet — 768×1024', () => {
  test.use(TABLET);

  test('/sectors donut / hero renders', async ({ page }) => {
    await page.goto('/sectors');
    await waitForAppReady(page);

    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  });
});
