import { expect, test } from '@playwright/test';

declare global {
  interface Window { __batch12DetailHistoryGap?: { patched: boolean; url: string }; }
}

test('county detail consumes a fiscal URL changed before history integration', async ({ page }) => {
  let calls = 0;
  await page.route(url => url.pathname === '/api/v1/counties/001/comprehensive'
    && url.searchParams.get('fiscal_year') === 'FY2024/25', async route => {
    calls++;
    const response = await route.fetch();
    expect(response.status()).toBe(200);
    const data = await response.json();
    delete data.id;
    await route.fulfill({ json: data });
  });
  await page.addInitScript(() => {
    const original = history.replaceState;
    let injected = false;
    history.replaceState = function (...args: Parameters<History['replaceState']>) {
      const result = Reflect.apply(original, this, args);
      // The initial router commit precedes its passive history-integration effect.
      if (!injected && args[0]?.__NA && location.pathname === '/counties/001') {
        injected = true;
        const patched = history.pushState.toString().includes('__NA');
        history.pushState({ batch12Owner: 'preserve-me' }, '', '/counties/001?fy=FY2024%2F25');
        window.__batch12DetailHistoryGap = { patched, url: location.href };
      }
      return result;
    };
  });
  await page.goto('/counties/001');
  await expect.poll(() => page.evaluate(() => window.__batch12DetailHistoryGap?.patched)).toBe(false);
  const origin = await page.evaluate(() => performance.timeOrigin);
  const historyLength = await page.evaluate(() => history.length);
  // Preserve the original request detector, malformed payload and 10s deadline.
  await expect.poll(() => calls).toBeGreaterThan(0);
  await expect(page.getByText(/Failed to load county data/i)).toBeVisible();
  await expect(page).toHaveURL(/fy=FY2024%2F25/);
  expect(await page.evaluate(() => history.state.batch12Owner)).toBe('preserve-me');
  expect(await page.evaluate(() => history.length)).toBe(historyLength);
  await page.evaluate(() => history.pushState(null, '', '/counties/001'));
  await expect(page.getByRole('heading', { name: 'Nairobi County', exact: true })).toBeVisible();
  expect(await page.evaluate(() => performance.timeOrigin)).toBe(origin);
});
