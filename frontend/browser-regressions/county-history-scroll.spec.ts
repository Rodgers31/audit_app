import { expect, test } from '@playwright/test';

test.use({ viewport: { width: 1128, height: 906 } });

// Separate from the original browser inventory. Exercise the browser's history
// restoration, including a forward transition interrupted by another Back.
test('rapid county history returns retain the saved list position', async ({ page }) => {
  await page.goto('/counties?p=2');
  await expect(page.getByText(/Showing\s+11[–\-]20\s+of/)).toBeVisible();
  const firstCounty = page.locator('table tbody tr').first().getByRole('link').first();
  // Position the link before measuring; a click's implicit auto-scroll is not
  // part of the list position that browser history is expected to restore.
  await firstCounty.scrollIntoViewIfNeeded();
  const listUrl = page.url();
  const saved = await page.evaluate(() => ({
    y: scrollY,
    height: document.documentElement.scrollHeight,
    viewport: innerHeight,
  }));
  expect(saved.y).toBeGreaterThan(100);
  const expectSavedPosition = async () => {
    let consecutiveMatches = 0;
    await expect.poll(async () => {
      const distance = await page.evaluate((y) => Math.abs(scrollY - y), saved.y);
      consecutiveMatches = distance < 2 ? consecutiveMatches + 1 : 0;
      return consecutiveMatches;
    }, { intervals: [100], timeout: 5000 }).toBeGreaterThanOrEqual(3);
  };
  await firstCounty.press('Enter');
  await expect(page).toHaveURL(/\/counties\/[\w-]+/);
  const detailUrl = page.url();
  await page.getByRole('link', { name: /All counties/i }).first().click();
  await expect(page).toHaveURL(listUrl);
  await expectSavedPosition();

  // Document-level smooth scrolling also animates native history restoration.
  // A rapid reverse can save an intermediate offset into the history entry.
  // User-initiated smooth scrolls opt in at their own call sites instead.
  expect(await page.evaluate(() => getComputedStyle(document.documentElement).scrollBehavior)).toBe('auto');
  for (let cycle = 0; cycle < 5; cycle++) {
    await page.goForward();
    // Check the traversal without waiting for detail rendering; the next Back
    // must still be able to interrupt the forward transition.
    expect(page.url()).toBe(detailUrl);
    await page.goBack();
    await expect(page).toHaveURL(listUrl);
    await expect(page.getByText(/Showing\s+11[–\-]20\s+of/)).toBeVisible();
    await expectSavedPosition();
  }
  expect(await page.evaluate(() => document.documentElement.scrollHeight)).toBe(saved.height);
});
