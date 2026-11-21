import { readFile } from 'node:fs/promises';
import { expect, test } from '@playwright/test';
import { countyResponse } from './utils/countyResponse';

const asAt = '2026-06-30';
const source = {
  publisher: 'Controller of Budget',
  title: 'County Governments Budget Implementation Review Report, FY2025/26',
  table: 'Table 2.10',
  url: 'https://cob.go.ke/synthetic-county-payables.pdf',
};

test('County Explorer uses the same dated unpaid bills in the list, map and download', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 360, height: 820 });
  await countyResponse(page, async route => {
    const response = await route.fetch();
    const counties = await response.json() as Array<{ name: string }>;
    const bills: Record<string, number> = { Nairobi: 2_400_000_000, Mombasa: 720_000_000, Kisumu: 0, Nandi: 15_200_000_000 };
    await route.fulfill({ json: counties.map(county => {
      const value = bills[county.name] ?? null;
      return {
        ...county,
        pending_bills: value,
        pending_bills_selection: { as_at: asAt },
        pending_bills_as_at: value == null ? null : county.name === 'Nandi' ? '2025-06-30' : asAt,
        pending_bills_source: value == null ? null : source,
        pending_bills_notes: county.name === 'Mombasa' ? [{ code: 'assembly_not_printed', table: source.table }] : [],
      };
    }) });
  });
  await page.getByRole('button', { name: 'Unpaid bills', exact: true }).press('Enter');
  const list = page.getByRole('list', { name: 'County Rankings' });
  const rows = list.getByRole('listitem');
  await expect(page.getByRole('combobox', { name: 'Budget year' })).toHaveValue('FY2024/25');
  const rankingHeader = page.getByRole('heading', { name: 'County Rankings', exact: true }).locator('..');
  await expect(rankingHeader.getByText('Unpaid bills · As at 30 June 2026', { exact: true })).toBeVisible();
  await expect(rows.nth(0)).toContainText('NairobiKES 2.4B');
  await expect(rows.nth(1)).toContainText('MombasaKES 720.0M');
  await expect(rows.nth(2)).toContainText('KisumuKES 0');
  await expect(rows.nth(2)).toHaveAttribute('data-unpaid-bills-tone', '1');
  await expect(rows.nth(3)).toContainText('No published figure');
  await page.getByRole('button', { name: /reverse sort direction/i }).press('Space');
  await expect(rows.nth(0)).toContainText('KisumuKES 0');
  await expect(rows.nth(2)).toContainText('NairobiKES 2.4B');
  await expect(rows.nth(3)).toContainText('No published figure');

  await page.getByRole('button', { name: 'Map', exact: true }).press('Enter');
  const map = page.getByRole('region', { name: 'County unpaid bills map' });
  await expect(map.locator('header time').first()).toHaveAttribute('datetime', asAt);
  await expect(map.getByRole('group', { name: 'Unpaid bills key' })).toContainText('KES 2.4B');
  const mombasa = map.getByRole('link', { name: 'Mombasa, Unpaid bills, KES 720.0M', exact: true });
  await expect(mombasa).toHaveAttribute('data-unpaid-bills-tone', '2');
  await mombasa.press('Space');
  const readout = map.locator('#county-map-readout');
  await expect(readout).toContainText('KES 720.0M');
  await expect(readout).toContainText('County Executive only');
  await expect(readout.getByRole('link', { name: 'Controller of Budget report · Table 2.10' })).toHaveAttribute('href', source.url);
  await expect(map.getByRole('link', { name: 'Nandi, Unpaid bills, No published figure', exact: true }))
    .toHaveAttribute('data-unpaid-bills-tone', 'unavailable');

  const pendingDownload = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export', exact: true }).click();
  const download = await pendingDownload;
  expect(download.suggestedFilename()).toBe(`county_unpaid_bills_${asAt}.csv`);
  const downloadPath = testInfo.outputPath(download.suggestedFilename());
  await download.saveAs(downloadPath);
  const [headers, first, second, third, ...rest] = (await readFile(downloadPath, 'utf8')).split('\n');
  expect(headers).toBe('"Rank","County","Unpaid bills (KES)","Reporting date","Source table","Source URL"');
  expect(first).toBe(`"1","Kisumu","0","${asAt}","Table 2.10","${source.url}"`);
  expect(second).toContain('"2","Mombasa","720000000"');
  expect(third).toContain('"3","Nairobi","2400000000"');
  expect(rest).toContain(`"","Nandi","","${asAt}","",""`);

  await page.getByRole('button', { name: 'Spending rate', exact: true }).press('Enter');
  await expect(page.getByRole('region', { name: 'County spending map' })).toBeVisible();
});
