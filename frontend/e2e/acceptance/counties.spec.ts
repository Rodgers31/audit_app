import { expect, test } from '@playwright/test';

// The API is a real FastAPI app with isolated synthetic SQLite records. Both
// Next server prefetch and browser requests see these same published/absent rows.
test('county table distinguishes a sourced amount, publisher zero and absence', async ({ page }) => {
  await page.goto('/counties');
  const nairobi = page.getByRole('row').filter({ hasText: 'Nairobi' });
  const mombasa = page.getByRole('row').filter({ hasText: 'Mombasa' });
  await expect(nairobi).toContainText('100.0B');
  await expect(nairobi).toContainText('0%');
  await expect(mombasa).toContainText('—');
  await expect(mombasa).not.toContainText('0%');
});

test('county fiscal-period selection fetches and renders that period', async ({ page }) => {
  await page.goto('/counties');
  await page.getByRole('button', { name: /Year: FY2025\/26 9M/ }).click();
  const response = page.waitForResponse(r => r.url().includes('fiscal_year=FY2024%2F25') && r.ok());
  await page.getByRole('button', { name: 'FY2024/25', exact: true }).click();
  await response;
  await expect(page.getByRole('row').filter({ hasText: 'Nairobi' })).toContainText('50.0B');
});
