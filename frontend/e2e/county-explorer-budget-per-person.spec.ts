import { expect, test, type Page } from '@playwright/test';

const previousYear = 'FY2024/25';
const recentYear = 'FY2025/26 9M';
const censusSource = {
  id: 87,
  title: '2019 Kenya Population and Housing Census Volume I: Population by County and Sub-County',
  publisher: 'Kenya National Bureau of Statistics',
  url: 'https://repository.knbs.or.ke/example-census',
  meta: { dataset_id: 'knbs_census_2019' },
};
const budgetSource = {
  id: 12,
  title: 'County Governments Budget Implementation Review Report',
  publisher: 'Controller of Budget',
  url: 'https://cob.go.ke/synthetic-county-budgets.pdf',
};
const fixture = [
  { entityId: 171, name: 'Nairobi', population: 100_000, allocation: 2e9 },
  { entityId: 172, name: 'Garissa', population: 1_000_000, allocation: 6e9 },
  { entityId: 173, name: 'Baringo', population: 300_000, allocation: 9e9 },
];

async function routeMeasures(page: Page) {
  let censusCalls = 0;
  let sourceCalls = 0;
  await page.route(url => url.pathname === '/api/v1/economic/population', route => {
    censusCalls++;
    expect(new URL(route.request().url()).searchParams.get('year')).toBe('2019');
    return route.fulfill({ json: fixture.map(county => ({
      year: 2019,
      entity_type: 'county',
      entity_id: county.entityId,
      entity_name: `${county.name} County`,
      total_population: county.population,
      source_document_id: censusSource.id,
    })) });
  });
  await page.route(url => url.pathname === `/api/v1/source-documents/${censusSource.id}`, route => {
    sourceCalls++;
    return route.fulfill({ json: censusSource });
  });
  await page.route(url => url.pathname === '/api/v1/counties' && url.searchParams.has('fiscal_year'), async route => {
    const response = await route.fetch();
    const counties = await response.json() as Array<{ name: string } & Record<string, unknown>>;
    const year = new URL(route.request().url()).searchParams.get('fiscal_year');
    await route.fulfill({ json: counties.map(county => {
      const row = fixture.find(item => item.name === county.name);
      if (!row) return county;
      return {
        ...county,
        financial_summary: {
          total_allocation: row.allocation * (year === recentYear ? 0.5 : 1),
          fiscal_period: { label: year },
          currency: 'KES',
          accounting_basis: 'reported_total',
          sources: [budgetSource],
        },
        figure_qualifications: { budget_lines: { 1: { allocated_amount: {
          status: county.name === 'Baringo' ? 'conflicting' : 'qualified',
          reason: 'historical_source_not_value_checked',
          source_document_id: budgetSource.id,
          publisher: budgetSource.publisher,
          source_url: budgetSource.url,
          identity: {
            entity_id: row.entityId, geography: `${row.name} County`, period: year,
            unit: 'KES', basis: 'actual', measure: 'allocated_amount', dimensions: { category: 'Total' },
          },
        } } } },
      };
    }) });
  });
  return () => ({ censusCalls, sourceCalls });
}

test('the compact list and map share sourced per-person values, coverage and reporting periods', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const calls = await routeMeasures(page);
  await page.goto('/counties');
  const year = page.getByRole('combobox', { name: 'Year' });
  await year.selectOption(previousYear);
  await expect(page.getByRole('list', { name: 'County Rankings' })).toBeVisible();
  expect(calls()).toEqual({ censusCalls: 0, sourceCalls: 0 });
  await page.getByRole('button', { name: 'Budget per person', exact: true }).click();

  const list = page.getByRole('list', { name: 'County Rankings' });
  await expect(list.getByRole('listitem').first()).toContainText('NairobiKES 20,000');
  await expect(list.getByRole('listitem').nth(1)).toContainText('GarissaKES 6,000');
  await expect(list.getByRole('listitem').filter({ hasText: 'Baringo' })).toContainText('No sourced amount');
  await expect(page.getByText('2 of 47 counties have a sourced figure.')).toBeVisible();
  await expect(page.getByRole('link', { name: '2019 KNBS Census' })).toHaveAttribute('href', censusSource.url);

  await page.getByRole('button', { name: /reverse sort direction/i }).click();
  await expect(list.getByRole('listitem').first()).toContainText('GarissaKES 6,000');

  await page.getByRole('button', { name: 'Map', exact: true }).click();
  const map = page.getByRole('region', { name: 'County budget per person map' });
  const nairobi = map.getByRole('link', { name: 'Nairobi, Budget per person, KES 20,000' });
  await expect(nairobi).toHaveAttribute('data-per-person-tone', '4');
  await expect(map.getByRole('link', { name: 'Baringo, Budget per person, No sourced amount' }))
    .toHaveAttribute('data-per-person-tone', 'unavailable');
  await nairobi.focus();
  await expect(map.locator('#county-map-readout')).toContainText('KES 20,000');
  await expect(map.getByRole('link', { name: 'Budget report' })).toHaveAttribute('href', budgetSource.url);

  await year.selectOption(recentYear);
  await expect(map.getByRole('link', { name: 'Nairobi, Budget per person, KES 10,000' })).toBeVisible();
  await page.getByRole('button', { name: 'List', exact: true }).click();
  await expect(list.getByRole('listitem').first()).toContainText('GarissaKES 3,000');
  expect(calls()).toEqual({ censusCalls: 1, sourceCalls: 1 });
});

test('desktop keeps per-person ranks on the selected measure and exports the same data with its sources', async ({ page }) => {
  await routeMeasures(page);
  await page.goto('/counties');
  await page.getByRole('combobox', { name: 'Year' }).selectOption(previousYear);
  await page.getByRole('button', { name: 'Budget per person', exact: true }).click();
  const table = page.getByRole('table', { name: 'County Rankings' });
  await expect(table.locator('tbody tr').first()).toContainText('NairobiKES 20,000');
  await table.getByRole('button', { name: 'Budget per person' }).click();
  await expect(table.locator('tbody tr').first()).toContainText('GarissaKES 6,000');

  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export' }).click();
  const file = await download;
  expect(file.suggestedFilename()).toBe('county_data_FY2024-25_budget_per_person.csv');
  const stream = await file.createReadStream();
  let csv = '';
  for await (const chunk of stream) csv += chunk.toString();
  expect(csv).toContain(`"1","Garissa","6000","${previousYear}","${budgetSource.url}","2019","${censusSource.url}"`);
  expect(csv).toContain('"","Baringo","","","","",""');
});
