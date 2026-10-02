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
