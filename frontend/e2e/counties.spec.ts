import { expect, test } from '@playwright/test';

test('counties explorer renders and interactions', async ({ page }) => {
  await page.goto('/counties');
  await page.getByPlaceholder('Type to search…').fill('Nairobi');
  const rows = page.locator('table tbody tr');
  await expect(rows).toHaveCount(1);
  await expect(rows.first()).toContainText('10.0B');
  await expect(rows.getByRole('cell', { name: 'No published rate' })).toBeVisible();
  await rows.getByRole('link', { name: 'Nairobi', exact: true }).click();
  await expect(page).toHaveURL(/\/counties\/001/);
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Nairobi County');
  await page.getByRole('tab', { name: 'Budget', exact: true }).click();
  await expect(page.locator('main')).toContainText('10.00B');
  await expect(page.getByRole('heading', { name: 'Budget Summary', exact: true })).toBeVisible();
  await expect(page.locator('main')).toContainText('KES 6.00B');
});

test.describe('county map with a touchscreen', () => {
  test.use({ hasTouch: true, viewport: { width: 390, height: 844 } });

  test('first tap selects a county and Open navigates', async ({ page }) => {
    await page.goto('/counties');
    await page.getByRole('button', { name: 'Map', exact: true }).tap();
    const map = page.getByRole('region', { name: 'County spending map' });
    const county = map.getByRole('link', { name: /^Garissa, Spending rate/ });

    await county.tap();
    await expect(page).toHaveURL(/\/counties$/);
    const summary = page.getByRole('dialog', { name: 'Garissa' });
    await expect(summary.getByRole('definition')).toHaveText('No published rate');
    await summary.getByRole('link', { name: 'Open Garissa' }).tap();
    await expect(page).toHaveURL(/\/counties\/007(?:\?|$)/);
  });

  test('Escape restores map focus so readers can open a different county summary', async ({ page }) => {
    await page.goto('/counties');
    await page.getByRole('button', { name: 'Map', exact: true }).tap();
    const map = page.getByRole('region', { name: 'County spending map' });
    const garissa = map.getByRole('link', { name: /^Garissa, Spending rate/ });
    const nairobi = map.getByRole('link', { name: /^Nairobi, Spending rate/ });

    await garissa.tap();
    const garissaSummary = page.getByRole('dialog', { name: 'Garissa' });
    await expect(garissaSummary.getByRole('link', { name: 'Open Garissa' })).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(garissaSummary).toBeHidden();
    await expect(garissa).toBeFocused();

    await nairobi.tap();
    await expect(page).toHaveURL(/\/counties$/);
    const nairobiSummary = page.getByRole('dialog', { name: 'Nairobi' });
    await expect(nairobiSummary.getByRole('link', { name: 'Open Nairobi' })).toBeVisible();
    await nairobiSummary.getByRole('link', { name: 'Open Nairobi' }).tap();
    await expect(page).toHaveURL(/\/counties\/001(?:\?|$)/);
  });

  test('a mouse click opens the county on a touchscreen device', async ({ page }) => {
    await page.goto('/counties');
    expect(await page.evaluate(() => matchMedia('(pointer: coarse)').matches)).toBe(true);
    await page.getByRole('button', { name: 'Map', exact: true }).tap();
    const map = page.getByRole('region', { name: 'County spending map' });
    const county = map.getByRole('link', { name: /^Garissa, Spending rate/ });

    await county.click();
    await expect(page).toHaveURL(/\/counties\/007(?:\?|$)/);
  });
});

test('county map Space selects and Enter opens a county', async ({ page }) => {
  await page.goto('/counties');
  await page.getByRole('button', { name: 'Map', exact: true }).click();
  const map = page.getByRole('region', { name: 'County spending map' });
  const county = map.getByRole('link', { name: /^Garissa, Spending rate/ });
  await county.focus();
  const scrollY = await page.evaluate(() => window.scrollY);

  await page.keyboard.press('Space');
  await expect(page).toHaveURL(/\/counties$/);
  await expect(county).toBeFocused();
  await expect(county).toHaveAttribute('aria-current', 'true');
  await expect(map.getByRole('link', { name: 'Open Garissa' })).toBeVisible();
  expect(await page.evaluate(() => window.scrollY)).toBe(scrollY);

  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/\/counties\/007(?:\?|$)/);
});

test('county map mouse hover previews and the first click opens', async ({ page }) => {
  await page.goto('/counties');
  await page.getByRole('button', { name: 'Map', exact: true }).click();
  const map = page.getByRole('region', { name: 'County spending map' });
  const county = map.getByRole('link', { name: /^Garissa, Spending rate/ });

  await county.hover();
  await expect(map.getByRole('link', { name: 'Open Garissa' })).toBeVisible();
  await expect(page).toHaveURL(/\/counties$/);

  await county.click();
  await expect(page).toHaveURL(/\/counties\/007(?:\?|$)/);
});
