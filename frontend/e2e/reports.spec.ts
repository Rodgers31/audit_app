import { expect, test } from '@playwright/test';

test('audit reports page filters and search', async ({ page }) => {
  await page.goto('/audits');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Audit Findings');
  await expect(page.locator('table').last().locator('tbody tr')).toHaveCount(20);
  await expect(page.locator('table').last().locator('tbody')).toContainText('KES 1.0M');
  const severity = page.getByText('Severity', { exact: true }).locator('..').getByRole('combobox');
  const response = page.waitForResponse(r => new URL(r.url()).pathname === '/api/v1/audit/findings' && new URL(r.url()).searchParams.get('severity') === 'Critical');
  await severity.selectOption('Critical');
  expect((await response).ok()).toBe(true);
  await expect(page.getByText('No findings match your filters.', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Clear filters', exact: true }).click();
  await expect(page.locator('table').last().locator('tbody tr')).toHaveCount(20);
  await expect(page.locator('table').last().locator('tbody')).toContainText('KES 1.0M');
});
