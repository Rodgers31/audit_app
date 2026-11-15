import { expect, test } from '@playwright/test';
import fixture from '../__tests__/fixtures/figure-qualifications.json';

test('exact observation evidence responds to the actual language controls without changing facts', async ({ page }) => {
  let requests = 0;
  await page.route('**/api/v1/provenance/verify/budget_lines?record_id=1', route => {
    requests += 1;
    return route.fulfill({ json: { value: '0', reason: null, qualifications: fixture.budget_lines.qualifications } });
  });
  await page.goto('/sources/figures/budget_lines/1');
  await expect(page.getByText('Stored value: 0')).toBeVisible();
  await page.locator('header summary').filter({ hasText: /^Language$/ }).click();
  for (const [name, title, value, technical, source, bytes] of [
    ['English', 'Observation evidence', 'Stored value: 0', 'Technical details', 'Open source document', 'Source bytes: checked · Value: matched'],
    ['Kiswahili', 'Ushahidi wa takwimu', 'Thamani iliyohifadhiwa: 0', 'Maelezo ya kiufundi', 'Fungua hati chanzo', 'Baiti za chanzo: zimekaguliwa · Thamani: imelingana'],
    ['Plain English', 'Evidence for this observation', 'Saved value: 0', 'Technical details', 'Open the source document', 'Source bytes: checked · Value: matched'],
  ]) {
    await page.getByRole('radio', { name, exact: true }).check();
    await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible();
    await expect(page.getByText(value, { exact: true })).toBeVisible();
    const receipt = page.locator('[data-figure-evidence]').getByRole('button');
    await receipt.click();
    const sheet = page.getByRole('dialog');
    await expect(sheet).toBeVisible();
    const disclosure = sheet.getByText(technical, { exact: true });
    const technicalDetails = sheet.locator('details');
    if (!await technicalDetails.evaluate(el => (el as HTMLDetailsElement).open)) await disclosure.click();
    await expect(sheet.getByText(bytes, { exact: true })).toBeVisible();
    await expect(sheet.getByText('Nairobi · FY2024/25 · KES · actual', { exact: true }).first()).toBeVisible();
    await expect(sheet.getByText(/^Central Bank of Kenya/).first()).toBeVisible();
    await expect(sheet.getByText(/json path \$\.observation/)).toBeVisible();
    await expect(sheet.getByRole('link', { name: source, exact: true }).first()).toHaveAttribute('href', 'https://www.centralbank.go.ke/data');
    await page.keyboard.press('Escape');
    await expect(receipt).toBeFocused();
  }
  expect(requests).toBe(1);
});

test('invalid exact references show a localized accessible refusal without a verification request', async ({ page }) => {
  let requests = 0;
  await page.route('**/api/v1/provenance/verify/**', route => { requests += 1; return route.abort(); });
  await page.goto('/sources/figures/unknown/0');
  await page.locator('header summary').filter({ hasText: /^Language$/ }).click();
  await page.getByRole('radio', { name: 'Kiswahili', exact: true }).check();
  await expect(page.getByRole('alert').filter({ hasText: 'Rejeo hili la takwimu si halali.' })).toHaveText('Rejeo hili la takwimu si halali.');
  await expect(page.getByRole('link', { name: 'Vyanzo vyote vya takwimu' })).toHaveAttribute('href', '/sources');
  expect(requests).toBe(0);
});
