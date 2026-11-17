import { expect, test } from '@playwright/test';
import fixture from '../__tests__/fixtures/figure-qualifications.json';

test('exact observation evidence responds to the actual language controls without changing facts', async ({ page }) => {
  let requests = 0;
  await page.route('**/api/v1/provenance/verify/budget_lines?record_id=1', route => {
    requests += 1;
    return route.fulfill({ json: { ...fixture.budget_lines, value: '0' } });
  });
  await page.goto('/sources/figures/budget_lines/1');
  await expect(page.getByRole('heading', { name: 'Budget allocation: 0' })).toBeVisible();
  const dates = page.locator('dl[aria-label="Source receipt"]');
  await expect(dates.getByText('Describes').locator('..')).toContainText('FY2024/25');
  await expect(dates.getByText('Source retrieved').locator('..')).toContainText('1 January 2026');
  await page.locator('header summary').filter({ hasText: /^Language$/ }).click();
  for (const [name, title, describes, technical, source, bytes] of [
    ['English', 'Budget allocation: 0', 'Describes', 'Technical details', 'Open source document', 'Source bytes: checked · Value: matched'],
    ['Kiswahili', 'Mgao wa bajeti: 0', 'Kipindi cha takwimu', 'Maelezo ya kiufundi', 'Fungua hati chanzo', 'Baiti za chanzo: zimekaguliwa · Thamani: imelingana'],
    ['Plain English', 'Budget allocation: 0', 'Describes', 'Technical details', 'Open the source document', 'Source bytes: checked · Value: matched'],
  ]) {
    await page.getByRole('radio', { name, exact: true }).check();
    await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible();
    await expect(page).toHaveTitle(`${title} | AuditGava`);
    await expect(page.getByText(describes, { exact: true })).toBeVisible();
    await expect(page.getByText('FY2024/25', { exact: true })).toBeVisible();
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

test('names the exact balance and links to the cited PDF page without inventing a retrieval date', async ({ page }) => {
  const source = 'https://example.test/synthetic-treasury-report.pdf';
  await page.route('**/api/v1/provenance/verify/loans?record_id=8', route => route.fulfill({
    json: {
      ...fixture.loans,
      value: 'KES 800,000 (Synthetic bond series A)',
      source_document: 'Synthetic Treasury report',
      source_url: source,
      fetch_date: null,
      reason: null,
      qualifications: {
        outstanding: {
          ...fixture.loans.qualifications.outstanding,
          identity: {
            ...fixture.loans.qualifications.outstanding.identity,
            period: '2026-06-30',
            dimensions: { lender: 'Synthetic bond series A' },
          },
          source_kind: 'pdf',
          source_url: source,
          locator: { table: '7', page: 12 },
        },
      },
    },
  }));
  await page.goto('/sources/figures/loans/8');
  const loadedTitle = 'Synthetic bond series A: KES 800,000';
  await expect(page.getByRole('heading', { name: loadedTitle })).toBeVisible();
  await expect(page).toHaveTitle(`${loadedTitle} | AuditGava`);
  await expect(page.locator('title')).toHaveCount(1);
  const receipt = page.locator('dl[aria-label="Source receipt"]');
  const link = receipt.getByRole('link', { name: 'Synthetic Treasury report · Table 7 · p. 12' });
  await expect(link).toHaveAttribute('href', `${source}#page=12`);
  await expect(receipt.getByText('Describes').locator('..')).toContainText('30 June 2026');
  await expect(receipt.getByText('Source retrieved').locator('..')).toContainText('Retrieval date not recorded');
  await expect(page.getByRole('button', { name: 'Refresh evidence' })).toHaveCount(0);
});

test('keeps disagreement visible without borrowing a document title or date from a different source', async ({ page }) => {
  await page.route('**/api/v1/provenance/verify/budget_lines?record_id=9', route => route.fulfill({
    json: {
      ...fixture.budget_lines,
      source_document: 'Another document',
      source_url: 'https://example.test/different.pdf',
      fetch_date: '2026-07-02T08:00:00Z',
      reason: 'conflicting_reporting_dates',
      qualifications: {
        allocated_amount: {
          ...fixture.budget_lines.qualifications.allocated_amount,
          status: 'conflicting',
          reason: 'conflicting_reporting_dates',
          identity: {
            ...fixture.budget_lines.qualifications.allocated_amount.identity,
            period: 'conflicting_reporting_dates',
          },
        },
      },
    },
  }));
  await page.goto('/sources/figures/budget_lines/9');
  const receipt = page.locator('dl[aria-label="Source receipt"]');
  await expect(receipt.getByText('The source dates disagree')).toBeVisible();
  await expect(receipt.getByText('Retrieval date not recorded')).toBeVisible();
  await expect(receipt.getByRole('link', { name: 'Central Bank of Kenya' })).toHaveAttribute('href', 'https://www.centralbank.go.ke/data');
  await expect(receipt.getByText('Another document')).toHaveCount(0);
  await page.locator('[data-figure-evidence]').getByRole('button').click();
  await expect(page.getByRole('dialog').getByText('Sources disagree', { exact: true })).toBeVisible();
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
