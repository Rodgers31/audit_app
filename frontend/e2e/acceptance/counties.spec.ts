import { expect, test } from '@playwright/test';

// The API is a real FastAPI app with isolated synthetic SQLite records. Both
// Next server prefetch and browser requests see these same published/absent rows.
test('county table distinguishes a sourced amount, publisher zero and absence', async ({ page }) => {
  await page.goto('/counties');
  await page.getByRole('button', { name: 'Table view', exact: true }).click();
  const nairobi = page.getByRole('row').filter({ hasText: 'Nairobi' });
  const mombasa = page.getByRole('row').filter({ hasText: 'Mombasa' });
  await expect(nairobi).toContainText('100.0B');
  await expect(nairobi.getByRole('cell', { name: '0.0% Reported for this period' })).toBeVisible();
  await expect(mombasa.getByRole('cell', { name: 'No published rate' })).toBeVisible();
});

test('county fiscal-period selection fetches and renders that period', async ({ page }) => {
  await page.goto('/counties');
  await page.getByRole('button', { name: 'Table view', exact: true }).click();
  const fiscalYear = page.getByRole('combobox', { name: 'Year', exact: true });
  await expect(fiscalYear).toHaveValue('FY2025/26 9M');
  const response = page.waitForResponse(r => r.url().includes('fiscal_year=FY2024%2F25') && r.ok());
  await fiscalYear.selectOption('FY2024/25');
  await response;
  await expect(fiscalYear).toHaveValue('FY2024/25');
  await expect(page.getByRole('row').filter({ hasText: 'Nairobi' })).toContainText('50.0B');
});
