import { expect, test } from '@playwright/test';
import { waitForAppReady } from './utils/selectors';

for (const delivery of ['pending', 'failed'] as const) {
  test(`pagination keeps URL and rows together with a ${delivery} server navigation`, async ({ page }) => {
    let release!: () => void;
    const gate = new Promise<void>(resolve => { release = resolve; });
    const responses: number[] = [];
    await page.route(url => url.pathname === '/counties' && url.searchParams.has('p') && url.searchParams.has('_rsc'), async route => {
      if (delivery === 'failed') return route.abort('failed');
      const response = await route.fetch();
      responses.push(response.status());
      await gate;
      await route.fulfill({ response });
    });
    try {
      await page.goto('/counties');
      await waitForAppReady(page);
      await expect(page.locator('table tbody tr')).toHaveCount(10);
      const documentOrigin = await page.evaluate(() => performance.timeOrigin);
      const historyLength = await page.evaluate(() => history.length);
      await page.getByRole('button', { name: '2', exact: true }).click();
      await expect(page.getByText(/Showing\s+11[–\-]20\s+of/)).toBeVisible();
      await expect(page).toHaveURL(/[?&]p=2/, { timeout: 5000 });
      expect(await page.evaluate(() => history.length)).toBe(historyLength);
      expect(await page.evaluate(() => performance.timeOrigin)).toBe(documentOrigin);
      expect(responses).toEqual([]);
    } finally {
      release();
      await page.unrouteAll({ behavior: 'wait' });
    }
  });
}

test('rapid pagination and view-all keep the latest list state without a server navigation', async ({ page }) => {
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  let navigations = 0;
  await page.route(url => url.pathname === '/counties' && url.searchParams.has('_rsc'), async route => {
    navigations++;
    const response = await route.fetch();
    await gate;
    await route.fulfill({ response });
  });
  try {
    await page.goto('/counties');
    await waitForAppReady(page);
    await expect(page.locator('table tbody tr')).toHaveCount(10);
    await page.getByRole('button', { name: '2', exact: true }).click();
    await expect(page.getByText(/Showing\s+11[–\-]20\s+of/)).toBeVisible();
    await page.getByRole('button', { name: '3', exact: true }).click();
    await expect(page.getByText(/Showing\s+21[–\-]30\s+of/)).toBeVisible();
    await page.getByRole('button', { name: /View All Counties|Kaunti Zote/i }).click();
    await expect(page.locator('table tbody tr')).toHaveCount(47);
    await expect(page).toHaveURL(/[?&]view=all/);
    expect(new URL(page.url()).searchParams.has('p')).toBe(false);
    expect(navigations).toBe(0);
  } finally {
    release();
    await page.unrouteAll({ behavior: 'wait' });
  }
  await expect(page).toHaveURL(/[?&]view=all/);
  await expect(page.locator('table tbody tr')).toHaveCount(47);
});
