import { expect, test } from '@playwright/test';

test('county Audit reveals every matching finding and restores focus to new results', async ({ page, request }) => {
  const path = '/api/v1/counties/001/comprehensive';
  const response = await request.get(path);
  expect(response.ok()).toBeTruthy();
  const county = await response.json();
  const source = 'https://example.test/audit.pdf#page=31';
  const excerpt = 'The comparison lists multiple unsupported financial entries for the first group. The Auditor-General included the detailed transaction records and their dates in the cited report.';
  const findings = Array.from({ length: 45 }, (_, index) => ({
    id: 8100 + index, finding: `Audit finding ${index + 1}\n${excerpt}`,
    audited_entity_name: 'County Executive', source_url: source, page_ref: 'p.31',
    category: index % 2 === 0 ? 'Payroll Issues' : 'other', severity: 'warning', status: 'open',
    amount_involved: 0, recommendation: 'Provide the original report.',
  }));
  await page.setViewportSize({ width: 360, height: 820 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.clock.setFixedTime(new Date(Date.now() + 2 * 60 * 60 * 1000));
  await page.route(url => url.pathname === path, route => route.fulfill({ json: {
    ...county, audit: { ...county.audit, findings_count: 45, findings, by_severity: { warning: 45 } },
    missing_funds: { ...county.missing_funds, cases: [] },
  } }));
  await page.goto('/counties/001?tab=audit');
  const all = page.getByRole('region', { name: 'All audit findings' });
  await expect(all.getByRole('status')).toHaveText('Showing 20 of 45 findings');
  const first = all.getByRole('article', { name: 'Audit finding 1', exact: true });
  const disclosure = first.locator('summary');
  await expect(disclosure).toHaveText('Read the Auditor’s words');
  await expect(first.locator('blockquote')).toBeHidden();
  await disclosure.press('Enter');
  await expect(first.locator('blockquote')).toBeVisible();
  await expect(first.locator('blockquote')).toHaveText(`Audit finding 1 ${excerpt}`);
  await expect(first.getByRole('link', { name: 'Source report, p.31' })).toHaveAttribute('href', source);
  await disclosure.press('Enter');
  await expect(first.locator('blockquote')).toBeHidden();

  await all.getByRole('button', { name: 'Show 20 more', exact: true }).press('Enter');
  await expect(all.getByRole('status')).toHaveText('Showing 40 of 45 findings');
  await expect(all.getByRole('heading', { name: 'Audit finding 21' })).toBeFocused();
  await all.getByRole('button', { name: 'Show 5 more' }).press('Enter');
  await expect(all.getByRole('article')).toHaveCount(45);
  await expect(all.getByRole('heading', { name: 'Audit finding 41' })).toBeFocused();

  const filter = page.getByRole('button', { name: /Payroll issues/ });
  await filter.click();
  await expect(filter).toHaveAttribute('aria-pressed', 'true');
  const matching = page.getByRole('region', { name: 'Payroll issues findings' });
  await expect(matching.getByRole('status')).toHaveText('Showing 20 of 23 findings');
  await matching.getByRole('button', { name: 'Show 3 more' }).press('Enter');
  await expect(matching.getByRole('status')).toHaveText('Showing 23 of 23 findings');
  await expect(matching.getByRole('heading', { name: 'Audit finding 41' })).toBeFocused();
  await expect(filter).toHaveAttribute('aria-pressed', 'true');
  await expect(matching.getByRole('article', { name: 'Audit finding 2', exact: true })).toHaveCount(0);
});
