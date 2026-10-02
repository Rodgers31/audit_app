import { expect, test } from '@playwright/test';

test('budget page filter toggles and chart renders', async ({ page }) => {
  await page.goto('/budget');
  await expect(page.getByRole('heading', { name: 'KES 180B approved for FY 2025/26' })).toBeVisible();
  await expect(page.getByText('Spending & net lending KES 150B', { exact: true })).toBeVisible();
  await expect(page.getByText('Tax revenue', { exact: true }).first().locator('..')).toContainText('80B');
  await expect(page.locator('.recharts-wrapper').first()).toBeVisible();
  await page.getByRole('button', { name: 'FY2024/25', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'KES 150B approved for FY 2024/25' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'KES 180B approved for FY 2025/26' })).toHaveCount(0);
});
