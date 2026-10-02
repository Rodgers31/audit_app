import { expect, test } from '@playwright/test';
import { waitForAppReady } from './utils/selectors';

test.beforeEach(async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  await waitForAppReady(page);
  await page.locator('#home-map').scrollIntoViewIfNeeded();
  await expect(page.locator('#home-map path.rsm-geography')).toHaveCount(47);
});

test.describe('Interactive Kenya Map', () => {
  test('map renders with all counties visible', async ({ page }) => {
    await expect(page.locator('#home-map').getByRole('group')).toBeVisible();
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
  for (const key of ['Enter', 'Space']) {
    test(`${key} opens the county action without a pointer`, async ({ page }) => {
      const map = page.locator('#home-map');
      await map.locator('path.rsm-geography').first().focus();
      await page.keyboard.press(key);
      await expect(map.getByRole('link', { name: 'View detailed analysis', exact: true }))
        .toHaveAttribute('href', '/counties/030?from=home-map');
    });
  }
  test('map has proper ARIA labels', async ({ page }) => {
    await expect(page.locator('#home-map').getByRole('group')).toHaveAccessibleName(/Kenya|county|counties/i);
  });
  test('map is keyboard navigable', async ({ page }) => {
    const map = page.locator('#home-map');
    const paths = map.locator('path.rsm-geography');
    await map.getByRole('button', { name: 'Focus', exact: true }).focus();
    await page.keyboard.press('Tab');
    await expect(paths.first()).toBeFocused();
    await expect(paths.first()).toHaveRole('button');
    await expect(paths.first()).toHaveAccessibleName('Baringo');
    await expect(paths.first()).toHaveCSS('outline-style', 'solid');
    await expect(map.getByRole('region')).toHaveCount(0);
    await page.keyboard.press('Enter');
    const baringo = map.getByRole('region', { name: 'Baringo', exact: true });
    await expect(baringo).toBeFocused();
    const detail = baringo.getByRole('link', { name: 'View detailed analysis', exact: true });
    await expect(detail).toHaveAttribute('href', '/counties/030?from=home-map');
    await page.keyboard.press('Tab');
    const close = baringo.getByRole('button', { name: 'Close Baringo tooltip', exact: true });
    await expect(close).toBeFocused();
    await page.keyboard.press('Tab');
    await expect(detail).toBeFocused();
    await page.keyboard.press('Shift+Tab');
    await page.keyboard.press('Enter');
    await expect(paths.first()).toBeFocused();
    await expect(baringo).toHaveCount(0);
    await page.keyboard.press('Tab');
    await expect(paths.nth(1)).toBeFocused();
    await expect(paths.nth(1)).toHaveAccessibleName('Bomet');
    const scrollBefore = await page.evaluate(() => window.scrollY);
    await page.keyboard.press('Space');
    const bomet = map.getByRole('region', { name: 'Bomet', exact: true });
    await expect(bomet).toBeFocused();
    await expect(bomet.getByRole('link', { name: 'View detailed analysis', exact: true }))
      .toHaveAttribute('href', '/counties/036?from=home-map');
    expect(await page.evaluate(() => window.scrollY)).toBe(scrollBefore);
    await page.keyboard.press('Escape');
    await expect(paths.nth(1)).toBeFocused();
    await expect(bomet).toHaveCount(0);
  });

  test('unmapped and unnamed geography cannot select a county', async ({ page }) => {
    await page.route('**/kenya-counties.topo.json', async route => {
      const response = await route.fetch();
      const topo = await response.json();
      const geometries = Object.values(topo.objects)[0] as { geometries: Array<{ properties: Record<string, string> }> };
      geometries.geometries[0].properties = { NAME_1: '' };
      geometries.geometries[1].properties = { NAME_1: 'Unmapped geography' };
      await route.fulfill({ response, json: topo });
    });
    await page.reload();
    const paths = page.locator('#home-map path.rsm-geography');
    await expect(paths).toHaveCount(47);
    await expect(page.locator('#home-map path[role="button"]')).toHaveCount(45);
    for (const path of [paths.first(), paths.nth(1)]) {
      await expect(path).toHaveAttribute('tabindex', '-1');
      await expect(path).not.toHaveAttribute('role', 'button');
      await path.click();
      await expect(page.locator('#home-map').getByRole('region')).toHaveCount(0);
    }
  });

  test('keyboard card persists across pointer leave and switching selection', async ({ page }) => {
    const map = page.locator('#home-map');
    const paths = map.locator('path.rsm-geography');
    await paths.first().focus();
    await page.keyboard.press('Enter');
    await paths.nth(1).hover();
    await page.mouse.move(0, 0);
    const baringo = map.getByRole('region', { name: 'Baringo', exact: true });
    await expect(baringo).toBeFocused();
    // Exceeds both existing hover-dismiss timers; this is a persistence control.
    await page.waitForTimeout(1400);
    await expect(baringo).toBeFocused();
    await paths.nth(1).focus();
    await page.keyboard.press('Space');
    const bomet = map.getByRole('region', { name: 'Bomet', exact: true });
    await expect(bomet).toBeFocused();
    await bomet.getByRole('button', { name: 'Close Bomet tooltip', exact: true }).click();
    await expect(paths.nth(1)).toBeFocused();
    await expect(bomet).toHaveCount(0);
    await page.mouse.move(0, 0);
    await paths.first().click();
    await expect(map.getByRole('region', { name: 'Baringo', exact: true })).toBeVisible();
    await expect(map.getByRole('link', { name: 'Explore Baringo', exact: true })).toBeVisible();
  });

  test('pointer selection switches a keyboard-open county card', async ({ page }) => {
    const map = page.locator('#home-map');
    const paths = map.locator('path.rsm-geography');
    await paths.first().focus();
    await page.keyboard.press('Enter');
    await expect(map.getByRole('region', { name: 'Baringo', exact: true })).toBeFocused();
    await paths.nth(1).click();
    await expect(map.getByRole('link', { name: 'Explore Bomet', exact: true })).toBeVisible();
    const card = map.getByRole('region', { name: 'Bomet', exact: true });
    await expect(card).toBeVisible();
    await expect(card.getByRole('link', { name: 'View detailed analysis', exact: true }))
      .toHaveAttribute('href', '/counties/036?from=home-map');
  });

  test('holding Space after county activation does not scroll', async ({ page }) => {
    const map = page.locator('#home-map');
    await map.locator('path.rsm-geography').first().focus();
    await page.keyboard.down('Space');
    await expect(map.getByRole('region', { name: 'Baringo', exact: true })).toBeFocused();
    const scrollBefore = await page.evaluate(() => window.scrollY);
    await page.keyboard.down('Space');
    await page.keyboard.down('Space');
    await page.keyboard.up('Space');
    // Observe past the browser's smooth key-scroll duration, not only keyup.
    await page.waitForTimeout(400);
    expect(await page.evaluate(() => window.scrollY)).toBe(scrollBefore);
  });

  test('keyboard county details stay within mobile bounds', async ({ page }) => {
    for (const width of [320, 375, 768, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      const map = page.locator('#home-map');
      await map.locator('path.rsm-geography').first().focus();
      await page.keyboard.press('Enter');
      const card = map.getByRole('region', { name: 'Baringo', exact: true });
      await expect(card).toBeFocused();
      const box = await card.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.x).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width).toBeLessThanOrEqual(width);
      const container = await map.getByRole('group').boundingBox();
      expect(container).not.toBeNull();
      expect(box!.x).toBeGreaterThanOrEqual(container!.x);
      expect(box!.x + box!.width).toBeLessThanOrEqual(container!.x + container!.width);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
      await page.keyboard.press('Escape');
    }
  });
});
