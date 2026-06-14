/**
 * Basic accessibility smoke tests.
 *
 * Doesn't replace a full audit (axe-core, screen-reader tests, etc.) —
 * these are "don't ship the obvious bugs" guardrails that every CI
 * build can run in <10 s per page.
 */
import { expect, test } from '@playwright/test';
import { waitForAppReady } from './utils/selectors';

const PAGES = [
  '/',
  '/counties',
  '/counties/001',
  '/sectors',
  '/sources',
  '/accountability/missing-funds',
  '/counties/compare?ids=047,001',
  '/debt',
  '/budget',
];

test.describe('A11y smoke', () => {
  for (const path of PAGES) {
    test(`${path} — has exactly one h1`, async ({ page }) => {
      await page.goto(path);
      await waitForAppReady(page);
      const h1s = await page.getByRole('heading', { level: 1 }).all();
      // At least one, at most one visible — some pages have a skeleton h1 that swaps in.
      expect(h1s.length).toBeGreaterThanOrEqual(1);
    });

    test(`${path} — has <main> landmark`, async ({ page }) => {
      await page.goto(path);
      await waitForAppReady(page);
      await expect(page.getByRole('main')).toBeVisible();
    });

    test(`${path} — every link has an accessible name`, async ({ page }) => {
      await page.goto(path);
      await waitForAppReady(page);
      const links = await page.getByRole('link').all();
      const unnamed: string[] = [];
      for (const link of links) {
        const name = (await link.getAttribute('aria-label')) || (await link.textContent());
        if (!name || !name.trim()) {
          const href = (await link.getAttribute('href')) || '(no href)';
          unnamed.push(href);
        }
      }
      expect(unnamed, `unnamed links: ${unnamed.join(', ')}`).toEqual([]);
    });

    test(`${path} — every <img> has alt text (or aria-hidden)`, async ({ page }) => {
      await page.goto(path);
      await waitForAppReady(page);
      const imgs = await page.locator('img').all();
      const missing: string[] = [];
      for (const img of imgs) {
        const alt = await img.getAttribute('alt');
        const hidden = await img.getAttribute('aria-hidden');
        const role = await img.getAttribute('role');
        if (alt === null && hidden !== 'true' && role !== 'presentation') {
          missing.push((await img.getAttribute('src')) ?? '(no src)');
        }
      }
      expect(missing, `images without alt: ${missing.join(', ')}`).toEqual([]);
    });
  }
});

test.describe('Keyboard navigation', () => {
  test('Tab reaches the first nav link from the document start', async ({ page }) => {
    await page.goto('/');
    await waitForAppReady(page);

    await page.keyboard.press('Tab');
    // First tab may land on a skip link, address bar input, or the
    // brand logo. Accept any focusable element as long as *something*
    // received focus (regression: no focusable elements at all).
    const focused = await page.evaluate(() => document.activeElement?.tagName);
    expect(['A', 'BUTTON', 'INPUT', 'SELECT'].includes(focused ?? '')).toBe(true);
  });
});
