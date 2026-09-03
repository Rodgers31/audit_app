import { expect, test } from '@playwright/test';

test('primary content remains visible when JavaScript is unavailable', async ({ browser, baseURL }) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();

  for (const route of ['/', '/privacy']) {
    const response = await page.goto(`${baseURL}${route}`, { waitUntil: 'load' });
    expect(response?.ok(), `${route} should return a successful document`).toBeTruthy();

    const heading = page.locator('h1').first();
    await expect(heading).toBeVisible();
    await expect(page.locator('main')).toBeVisible();
    await expect(heading).not.toHaveCSS('opacity', '0');
  }

  await context.close();
});
