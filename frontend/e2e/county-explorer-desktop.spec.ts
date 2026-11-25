import { expect, test } from '@playwright/test';

test.use({ viewport: { width: 1280, height: 900 } });

test('the ranked list and map share the selected county and retain its fiscal link', async ({ page }) => {
  await page.goto('/counties?retained=one');
  const list = page.getByRole('list', { name: 'County Rankings' });
  const map = page.getByRole('region', { name: 'County spending map' });
  const table = page.getByRole('table', { name: 'County Rankings' });
  await expect(list).toBeVisible();
  await expect(map).toBeVisible();
  await expect(table).toHaveCount(0);

  const left = await list.boundingBox();
  const right = await map.boundingBox();
  expect(left && right && left.x + left.width < right.x).toBe(true);

  const first = list.getByRole('listitem').nth(0);
  const second = list.getByRole('listitem').nth(1);
  await first.getByRole('checkbox').check();
  await second.getByRole('checkbox').check();

  await page.getByRole('searchbox').fill('Mombasa');
  const county = list.getByRole('button', { name: /Mombasa/ });
  await county.press('Enter');
  await expect(county).toBeFocused();
  await expect(county).toHaveAttribute('aria-pressed', 'true');
  await expect(map.getByRole('heading', { name: 'Mombasa County', exact: true })).toBeVisible();
  await expect(map.getByRole('button', { name: /^Mombasa,/ })).toHaveAttribute('aria-pressed', 'true');
  const year = await page.getByRole('combobox', { name: 'Year' }).inputValue();
  await expect(map.getByRole('link', { name: /Open Mombasa/ })).toHaveAttribute('href', `/counties/047?fy=${encodeURIComponent(year)}`);
  await expect(map.getByRole('button', { name: /Sources.*Mombasa budget|Source:.*Mombasa budget/i })).toBeVisible();

  const tableToggle = page.getByRole('button', { name: 'Table view' });
  await tableToggle.press('Space');
  await expect(tableToggle).toHaveAttribute('aria-pressed', 'true');
  await expect(table).toBeVisible();
  await expect(map).toHaveCount(0);
  expect(new URL(page.url()).searchParams.get('retained')).toBe('one');
  expect(new URL(page.url()).searchParams.get('layout')).toBe('table');

  await tableToggle.press('Space');
  await expect(list).toBeVisible();
  await expect(map.getByRole('heading', { name: 'Mombasa County', exact: true })).toBeVisible();
  await expect(page.getByRole('complementary', { name: 'Selected counties for comparison' })).toContainText('2 selected');
  expect(new URL(page.url()).searchParams.has('layout')).toBe(false);
});

test('desktop map activation reveals the same ranked row and the table keeps its header and sources', async ({ page }) => {
  await page.goto('/counties');
  const map = page.getByRole('region', { name: 'County spending map' });
  const list = page.getByRole('list', { name: 'County Rankings' });
  await map.getByRole('button', { name: /^Nairobi,/ }).press('Space');
  await expect(map.getByRole('heading', { name: 'Nairobi County', exact: true })).toBeVisible();
  await expect(list.getByRole('button', { name: /Nairobi/ })).toHaveAttribute('aria-pressed', 'true');

  await page.getByRole('button', { name: 'Table view' }).click();
  await page.getByRole('button', { name: 'View All Counties' }).click();
  const region = page.getByRole('region', { name: 'Sortable county table' });
  const table = region.getByRole('table', { name: 'County Rankings' });
  await expect(table.locator('tbody tr')).toHaveCount(47);
  await region.evaluate(element => { element.scrollTop = 220; });
  const headingTop = await table.getByRole('columnheader', { name: 'County', exact: true }).evaluate(element => element.getBoundingClientRect().top);
  const regionTop = await region.evaluate(element => element.getBoundingClientRect().top);
  expect(Math.abs(headingTop - regionTop)).toBeLessThan(3);

  const evidence = table.getByRole('button', { name: /Sources.*Nairobi budget|Source:.*Nairobi budget/i });
  await expect(evidence).toBeVisible();
  const icon = await evidence.boundingBox();
  expect(icon && icon.width >= 44 && icon.height >= 44).toBe(true);
  await evidence.press('Enter');
  const sheet = page.getByRole('dialog', { name: 'Where this figure comes from' });
  await expect(sheet).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(evidence).toBeFocused();
});
