import { expect, test } from '@playwright/test';

test('county Budget shows the nine-month report allocation and preserves exact source and statutory receipt links', async ({ page, request }) => {
  const countyPath = '/api/v1/counties/001/comprehensive';
  const response = await request.get(countyPath);
  expect(response.ok()).toBeTruthy();
  const county = await response.json();
  const source = { id: 91, publisher: 'Controller of Budget', title: 'Synthetic nine-month budget report',
    url: 'https://example.test/county-budget-9m.pdf' };
  const label = 'FY2025/26 9M';
  const allocation = (category: string) => ({ allocated_amount: {
    status: 'qualified', reason: 'historical_source_not_value_checked',
    identity: { measure: 'allocated_amount', entity_id: 91, geography: county.name, period: label,
      unit: 'KES', basis: 'actual', dimensions: { category, subcategory: null } },
    source_document_id: source.id, source_url: source.url,
  } });
  await page.setViewportSize({ width: 360, height: 840 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.clock.setFixedTime(new Date(Date.now() + 2 * 60 * 60 * 1000));
  await page.route(url => url.pathname === countyPath, route => route.fulfill({ json: {
    ...county,
    budget: {
      ...county.budget, fiscal_year: label, accounting_basis: 'reported_total', sources: [source], source: null,
      fiscal_period: { id: 9, label, start_date: '2025-07-01', end_date: '2026-03-31' },
      total_allocated: 10e9, development_budget: 4e9, recurrent_budget: 6e9,
      figure_qualifications: { '91': allocation('Total'), '92': allocation('Development'), '93': allocation('Recurrent') },
    },
  } }));
  await page.goto('/counties/001?tab=budget');
  const split = page.getByRole('region', { name: 'Budget split' });
  await expect(split.getByRole('meter')).toHaveAttribute('aria-valuetext', '40% for development');
  await expect(split.locator(':scope > p').filter({ hasText: /FY2025\/26 9M.*1 July 2025 to 31 March 2026/ })).toBeVisible();
  await expect(split.getByText('30% medium-term benchmark')).toBeVisible();
  await expect(split.getByText(/On track|compliant/i)).toHaveCount(0);

  const sourceReceipt = split.getByRole('button', { name: /Development allocation source and rule/ });
  await sourceReceipt.click();
  const dialog = page.getByRole('dialog', { name: 'Development allocation source and rule' });
  await expect(dialog.getByText(/KES 4,000,000,000 and recurrent KES 6,000,000,000.*KES 10,000,000,000/)).toBeVisible();
  await expect(dialog.getByRole('link', { name: source.title })).toHaveAttribute('href', source.url);
  await expect(dialog.getByRole('link', { name: 'Public Finance Management Act, section 107(2)(b)' }))
    .toHaveAttribute('href', 'https://pdmo.treasury.go.ke/publications/128/download#page=99');
  await dialog.press('Escape');
  await expect(sourceReceipt).toBeFocused();
});
