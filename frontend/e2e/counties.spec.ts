import { expect, test } from '@playwright/test';

test('counties explorer renders and interactions', async ({ page }) => {
  await page.goto('/counties');
  await page.getByPlaceholder('Type to search…').fill('Nairobi');
  const rows = page.locator('table tbody tr');
  await expect(rows).toHaveCount(1);
  await expect(rows.first()).toContainText('10.0B');
  await expect(rows.first()).toContainText('60%');
  await rows.getByRole('link', { name: 'Nairobi', exact: true }).click();
  await expect(page).toHaveURL(/\/counties\/001/);
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Nairobi County');
  await page.getByRole('button', { name: 'Budget & Debt', exact: true }).click();
  await expect(page.locator('main')).toContainText('10.00B');
  await expect(page.getByRole('heading', { name: 'Budget Summary', exact: true })).toBeVisible();
  await expect(page.locator('main')).toContainText('KES 6.00B');
});

test.describe('county map with a touchscreen', () => {
  test.use({ hasTouch: true, viewport: { width: 390, height: 844 } });

  test('first tap selects a county and Open navigates', async ({ page }) => {
    await page.goto('/counties');
    const map = page.getByRole('region', { name: 'County Performance Map' });
    const county = map.getByRole('link', { name: /^Garissa, Grade:/ });

    await county.tap();
    await expect(page).toHaveURL(/\/counties$/);
    await expect(county).toHaveAttribute('aria-current', 'true');
    await expect(map.getByRole('definition').filter({ hasText: 'KES 10.0B' })).toBeVisible();

    await map.getByRole('link', { name: 'Open Garissa' }).tap();
    await expect(page).toHaveURL(/\/counties\/007(?:\?|$)/);
  });

  test('a different county needs its own first tap before a second tap opens it', async ({ page }) => {
    await page.goto('/counties');
    const map = page.getByRole('region', { name: 'County Performance Map' });
    const garissa = map.getByRole('link', { name: /^Garissa, Grade:/ });
    const nairobi = map.getByRole('link', { name: /^Nairobi, Grade:/ });

    await garissa.tap();
    await expect(map.getByRole('link', { name: 'Open Garissa' })).toBeVisible();
    await nairobi.tap();
    await expect(page).toHaveURL(/\/counties$/);
    await expect(nairobi).toHaveAttribute('aria-current', 'true');
    await expect(garissa).not.toHaveAttribute('aria-current', 'true');
    await expect(map.getByRole('link', { name: 'Open Nairobi' })).toBeVisible();

    await nairobi.tap();
    await expect(page).toHaveURL(/\/counties\/001(?:\?|$)/);
  });
});

test('county map Space selects and Enter opens a county', async ({ page }) => {
  await page.goto('/counties');
  const map = page.getByRole('region', { name: 'County Performance Map' });
  const county = map.getByRole('link', { name: /^Garissa, Grade:/ });
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
  const map = page.getByRole('region', { name: 'County Performance Map' });
  const county = map.getByRole('link', { name: /^Garissa, Grade:/ });

  await county.hover();
  await expect(map.getByRole('link', { name: 'Open Garissa' })).toBeVisible();
  await expect(page).toHaveURL(/\/counties$/);

  await county.click();
  await expect(page).toHaveURL(/\/counties\/007(?:\?|$)/);
});
