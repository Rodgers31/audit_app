import { expect, test } from '@playwright/test';
import { countyResponse } from './utils/countyResponse';

const period = 'FY2024/25';

function reportTotal(county: { name: string; id: string }, measure: string, status: string) {
  return {
    status, reason: status === 'qualified' ? 'historical_source_not_value_checked' : 'multiple_observation_evidence',
    source_kind: 'pdf', identity: {
      measure, entity_id: Number(county.id), geography: `${county.name} County`, period, unit: 'KES', basis: 'actual',
      dimensions: { category: 'Total', subcategory: null, line_type: 'total' },
    },
    source_document_id: 20, publisher: 'Controller of Budget', source_url: 'https://cob.go.ke/synthetic-explorer.pdf',
    receipt_id: null, digest: null, locator: null, document_bytes_checked: false, value_checked: false,
  };
}

test.describe('mobile Explorer rankings', () => {
  test.use({ viewport: { width: 360, height: 820 }, hasTouch: true, reducedMotion: 'reduce' });

  test('opens the actual inventory after the top ten and compares selected counties by touch and keyboard', async ({ page }) => {
    await page.goto('/counties?retained=one&retained=two#county-list-anchor');
    const list = page.getByRole('list', { name: 'County Rankings' });
    await expect(list.getByRole('listitem')).toHaveCount(10);
    await expect(page.getByRole('table', { name: 'County Rankings' })).toHaveCount(0);
    await page.getByRole('button', { name: 'Show all 47 counties' }).tap();
    await expect(list.getByRole('listitem')).toHaveCount(47);
    await expect(page.getByText('Showing all 47 Counties', { exact: true })).toBeVisible();
    await expect(page.getByText('(1–10 of 47)', { exact: true })).toHaveCount(0);
    const url = new URL(page.url());
    expect(url.searchParams.get('view')).toBe('all');
    expect(url.searchParams.getAll('retained')).toEqual(['one', 'two']);
    expect(url.hash).toBe('#county-list-anchor');
    await page.getByRole('button', { name: 'Show Paginated' }).tap();
    await expect(list.getByRole('listitem')).toHaveCount(10);

    const first = list.getByRole('listitem').first();
    const second = list.getByRole('listitem').nth(1);
    const selectedIds = await Promise.all([first, second].map(row => row.getByRole('link').getAttribute('href')));
    await first.locator('label').tap();
    await expect(first.getByRole('checkbox')).toBeChecked();
    await second.getByRole('checkbox').press('Space');
    await expect(second.getByRole('checkbox')).toBeChecked();
    const tray = page.getByRole('complementary', { name: 'Selected counties for comparison' });
    await expect(tray.getByText('2 selected', { exact: true })).toBeVisible();
    const compare = tray.getByRole('link', { name: 'Compare', exact: true });
    const ids = selectedIds.map(href => href!.match(/\/counties\/([^?]+)/)![1]);
    await expect(compare).toHaveAttribute('href', `/counties/compare?ids=${ids.join(',')}`);
    await compare.press('Enter');
    await expect(page).toHaveURL(/\/counties\/compare\?ids=/);
    expect(new URL(page.url()).searchParams.get('ids')).toBe(ids.join(','));
  });

  test('ranks supported spending first in both directions and leaves conflicting or missing figures unranked', async ({ page }) => {
    await countyResponse(page, async route => {
      const response = await route.fetch();
      const data = await response.json() as Array<{ id: string; name: string } & Record<string, unknown>>;
      const rates: Record<string, number> = { Nairobi: 60, Mombasa: 72, Kisumu: 0, Baringo: 99 };
      await route.fulfill({ json: data.map(county => {
        const rate = rates[county.name];
        const status = county.name === 'Baringo' ? 'conflicting' : 'qualified';
        const budget_lines = rate == null ? {} : { '20': {
          allocated_amount: reportTotal(county, 'allocated_amount', status),
          actual_spent: reportTotal(county, 'actual_spent', status),
        } };
        return { ...county, budget_utilization: rate ?? 96, figure_qualifications: { budget_lines } };
      }) });
    });
    const list = page.getByRole('list', { name: 'County Rankings' });
    await page.getByRole('combobox', { name: /County Rankings.*Sort by/ }).selectOption('utilization');
    await expect(list.getByRole('listitem').nth(0)).toContainText('Mombasa72.0%');
    await expect(list.getByRole('listitem').nth(1)).toContainText('Nairobi60.0%');
    await expect(list.getByRole('listitem').nth(2)).toContainText('Kisumu0.0%');
    await expect(list.getByRole('listitem').nth(3)).toContainText('Not published');
    await expect(list.getByText('Below the 70% target', { exact: true })).toHaveCount(2);
    await page.getByRole('button', { name: /reverse sort direction/i }).click();
    await expect(list.getByRole('listitem').nth(0)).toContainText('Kisumu0.0%');
    await expect(list.getByRole('listitem').nth(2)).toContainText('Mombasa72.0%');
    await expect(list.getByRole('listitem').nth(3)).toContainText('Not published');
  });
});

test('desktop View all header and the Health explanation keep the existing Explorer route', async ({ page }) => {
  await page.goto('/counties?view=all');
  const table = page.getByRole('table', { name: 'County Rankings' });
  await expect(table.locator('tbody tr')).toHaveCount(47);
  await expect(page.getByText('Showing all 47 Counties', { exact: true })).toBeVisible();
  await expect(page.getByText('(1–10 of 47)', { exact: true })).toHaveCount(0);
  await page.getByText('Year', { exact: true }).locator('..').getByRole('combobox').selectOption(period);
  const health = table.getByRole('button', { name: /Explain Nairobi financial health grade/ });
  await health.press('Enter');
  const sheet = page.getByRole('dialog', { name: 'Financial Health Score' });
  await expect(sheet.getByText(/site-made composite score.*separate from the accountability score/)).toBeVisible();
  await expect(page).toHaveURL('/counties?view=all');
  await page.keyboard.press('Escape');
  await expect(sheet).toBeHidden();
  await expect(health).toBeFocused();
});
