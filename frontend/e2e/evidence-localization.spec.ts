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
  for (const [pill, title, value, summary, source, bytes] of [
    ['EN', 'Observation evidence', 'Stored value: 0', 'Evidence for this observation', 'Open source document', 'Source bytes: checked · Value: matched'],
    ['SW', 'Ushahidi wa takwimu', 'Thamani iliyohifadhiwa: 0', 'Ushahidi wa takwimu hii', 'Fungua hati chanzo', 'Baiti za chanzo: zimekaguliwa · Thamani: imelingana'],
    ['Aa', 'Evidence for this observation', 'Saved value: 0', 'Evidence for this observation', 'Open the source document', 'Source bytes: checked · Value: matched'],
  ]) {
    await page.getByRole('radio', { name: pill, exact: true }).click();
    await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible();
    await expect(page.getByText(value, { exact: true })).toBeVisible();
    const details = page.locator('details[data-figure-evidence]');
    await expect(details.locator('summary')).toContainText(summary);
    if (!await details.evaluate(el => (el as HTMLDetailsElement).open)) await details.locator('summary').click();
    await expect(details.getByText(bytes, { exact: true })).toBeVisible();
    await expect(details.getByText('Nairobi · FY2024/25 · KES · actual', { exact: true }).first()).toBeVisible();
    await expect(details.getByText(/Central Bank of Kenya/).first()).toBeVisible();
    await expect(details.getByText(/json path \$\.observation/)).toBeVisible();
    await expect(details.getByRole('link', { name: source, exact: true }).first()).toHaveAttribute('href', 'https://www.centralbank.go.ke/data');
  }
  expect(requests).toBe(1);
});

test('invalid exact references show a localized accessible refusal without a verification request', async ({ page }) => {
  let requests = 0;
  await page.route('**/api/v1/provenance/verify/**', route => { requests += 1; return route.abort(); });
  await page.goto('/sources/figures/unknown/0');
  await page.getByRole('radio', { name: 'SW', exact: true }).click();
  await expect(page.getByRole('alert').filter({ hasText: 'Rejeo hili la takwimu si halali.' })).toHaveText('Rejeo hili la takwimu si halali.');
  await expect(page.getByRole('link', { name: 'Vyanzo vyote vya takwimu' })).toHaveAttribute('href', '/sources');
  expect(requests).toBe(0);
});
