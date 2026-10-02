import { expect, test } from '@playwright/test';
import { waitForAppReady } from './utils/selectors';

test('home dashboard renders and allows county selection via map', async ({ page }) => {
  await page.goto('/');
  await waitForAppReady(page);
  const map = page.locator('#home-map');
  await map.scrollIntoViewIfNeeded();
  await expect(map.locator('path.rsm-geography')).toHaveCount(47);
  await map.locator('path.rsm-geography').first().click();
  await expect(map.getByRole('link', { name: 'Explore Baringo', exact: true })).toBeVisible();
  await expect(map).toContainText('KES 10.0B');
  await expect(map).toContainText('60.0%');
  await expect(map).toContainText('Synthetic browser finding');
});
