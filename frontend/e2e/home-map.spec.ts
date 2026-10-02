import { expect, test } from '@playwright/test';
import { waitForAppReady } from './utils/selectors';

test.beforeEach(async ({ page }) => {
  await page.goto('/');
  await waitForAppReady(page);
  await page.locator('#home-map').scrollIntoViewIfNeeded();
  await expect(page.locator('#home-map path.rsm-geography')).toHaveCount(47);
});

test.describe('Interactive Kenya Map', () => {
  test('map renders with all counties visible', async ({ page }) => {
    await expect(page.locator('#home-map').getByRole('application')).toBeVisible();
    await expect(page.locator('#home-map')).toContainText('47 counties');
  });
  test('clicking county on map updates county details', async ({ page }) => {
    await page.locator('#home-map path.rsm-geography').first().click();
    const link = page.locator('#home-map').getByRole('link', { name: 'Explore Baringo', exact: true });
    await expect(link).toHaveAttribute('href', '/counties/baringo');
    await expect(page.locator('#home-map')).toContainText('KES 10.0B');
  });
  test('map tooltip shows county info on hover', async ({ page }) => {
    await page.locator('#home-map path.rsm-geography').first().hover();
    await expect(page.locator('#home-map').getByText('County overview', { exact: true })).toBeVisible();
    await expect(page.locator('#home-map')).toContainText('Utilisation');
    await expect(page.locator('#home-map')).toContainText('1 found');
  });
  test('map visualization mode toggle works', async ({ page }) => {
    const focus = page.locator('#home-map').getByRole('button', { name: 'Focus', exact: true });
    await focus.click();
    await expect(focus).toHaveClass(/bg-gov-forest/);
    const all = page.locator('#home-map').getByRole('button', { name: 'All', exact: true });
    await all.click();
    await expect(all).toHaveClass(/bg-gov-forest/);
    await expect(focus).not.toHaveClass(/bg-gov-forest/);
  });
  test('selecting county updates URL or state', async ({ page }) => {
    await page.locator('#home-map path.rsm-geography').first().click();
    await page.locator('#home-map').getByRole('link', { name: 'Explore Baringo', exact: true }).click();
    await expect(page).toHaveURL(/\/counties\/baringo/);
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Baringo County');
  });
  // The quick slider was removed from the dashboard. Its old conditional test
  // silently passed without executing a selection. Named quarantine: #291.
  test.fixme('map integrates with county slider', async () => {});
  test('map county hover highlights corresponding area', async ({ page }) => {
    const path = page.locator('#home-map path.rsm-geography').first();
    await page.mouse.move(0, 0);
    const before = await path.evaluate(el => getComputedStyle(el).fill);
    await path.hover();
    await expect.poll(() => path.evaluate(el => getComputedStyle(el).fill)).not.toBe(before);
  });
});

test.describe('Map Accessibility', () => {
  test('map has proper ARIA labels', async ({ page }) => {
    await expect(page.locator('#home-map').getByRole('application')).toHaveAccessibleName(/Kenya|county|counties/i);
  });
  // Geography paths currently lack an Enter/Space activation handler. A Tab
  // landing anywhere on the page never proved keyboard selection. #291.
  test.fixme('map is keyboard navigable', async () => {});
});
