import { expect, test } from '@playwright/test';
import maturities from './fixtures/debt_maturities.json';
import { registerApiMocks } from './utils/mockApi';

const endpoint = '**/api/v1/debt/instruments';
test.beforeEach(async ({ page }) => { await registerApiMocks(page); });

test('anchors the takeaways to the register date and supports keyboard, hover and exact values', async ({ page }) => {
  await page.route(endpoint, route => route.fulfill({ json: maturities }));
  await page.goto('/debt');
  const section = page.getByRole('region', { name: 'When it’s due' });
  await expect(section.getByText('due 2029–2033', { exact: true }).locator('..')).toContainText('KES 940B');
  await expect(section.getByText('in 2034 alone · peak', { exact: true }).locator('..')).toContainText('KES 431.2B');
  const chart = section.getByRole('button', { name: 'Explore Treasury bond maturity years' });
  const readout = section.locator('[aria-live=polite]');
  await chart.focus();
  await expect(readout).toHaveText('2029 · KES 260,000,000,000');
  await page.keyboard.press('ArrowDown');
  await expect(readout).toHaveText('2030 · KES 175,000,000,000');
  await page.keyboard.press('End');
  await expect(readout).toContainText('2049');
  await page.keyboard.press('Enter');
  await expect(chart).toHaveAttribute('aria-pressed', 'true');
  await page.keyboard.press('Escape');
  await expect(chart).toHaveAttribute('aria-pressed', 'false');

  const peak = section.locator('li[data-signal=peak]');
  await peak.scrollIntoViewIfNeeded();
  const peakBounds = await peak.boundingBox();
  expect(peakBounds).not.toBeNull();
  await page.mouse.move(peakBounds!.x + 100, peakBounds!.y + peakBounds!.height / 2);
  await expect(readout).toHaveText('2034 · KES 431,240,000,001.25 · Peak');

  await section.getByText('What’s included?', { exact: true }).click();
  await expect(section.getByText(/Register snapshot dated 11 October 2028/)).toBeVisible();
  await expect(section.getByText(/59.2% of the CBK’s published Treasury-bond stock/)).toBeVisible();
  await expect(section.getByText(/2 securities were excluded/)).toBeVisible();
  await expect(section.getByText(/3 stored bond records were withheld/)).toContainText('before those publication checks');
  await expect(section.getByRole('link', { name: /Central Bank of Kenya source/ })).toHaveAttribute('href', maturities.source.url);
  await section.getByText('Read chart data', { exact: true }).click();
  await expect(section.getByRole('row', { name: /2034 Peak KES 431,240,000,001.25 5/ })).toBeVisible();
});

test.describe('on a phone', () => {
  test.use({ hasTouch: true, viewport: { width: 360, height: 820 }, reducedMotion: 'reduce' });

  test('taps a compact annual row to pin or clear its exact amount', async ({ page }) => {
    await page.route(endpoint, route => route.fulfill({ json: maturities }));
    await page.goto('/debt');
    const section = page.getByRole('region', { name: 'When it’s due' });
    const chart = section.getByRole('button', { name: 'Explore Treasury bond maturity years' });
    const readout = section.locator('[aria-live=polite]');
    const fifth = section.locator('li[data-signal=near]').nth(4);
    await fifth.scrollIntoViewIfNeeded();
    const bounds = await fifth.boundingBox();
    expect(bounds).not.toBeNull();
    await page.touchscreen.tap(bounds!.x + 40, bounds!.y + bounds!.height / 2);
    await expect(readout).toHaveText('2033 · KES 135,000,000,000');
    await page.touchscreen.tap(bounds!.x + 40, bounds!.y + bounds!.height / 2);
    await expect(chart).toHaveAttribute('aria-pressed', 'false');
    await page.touchscreen.tap(bounds!.x + 40, bounds!.y + bounds!.height / 2);
    await section.getByText('What’s included?', { exact: true }).tap();
    await expect(chart).toHaveAttribute('aria-pressed', 'false');
  });
});

test('shows signed, zero, missing and earlier rows without treating them as five-year dues', async ({ page }) => {
  await page.route(endpoint, route => route.fulfill({ json: {
    ...maturities,
    ladder: [
      { year: 2026, face_value: 9e9, instruments: 1 },
      { year: 2029, face_value: null, instruments: null },
      { year: 2030, face_value: 0, instruments: 0 },
      { year: 2031, face_value: -300, instruments: 2 },
      { year: 2034, face_value: 100, instruments: 1 },
    ],
  } }));
  await page.goto('/debt');
  const section = page.getByRole('region', { name: 'When it’s due' });
  await expect(section.getByText('reported for 2029–2033', { exact: true }).locator('..')).toContainText('KES 0');
  await expect(section.getByText(/Some years have no usable amount/)).toBeVisible();
  await expect(section.getByText('in 2034 alone · peak', { exact: true }).locator('..')).toContainText('KES 100');
  await section.getByText('Read chart data', { exact: true }).click();
  const table = section.getByRole('table');
  await expect(table.getByRole('row', { name: /2026 Earlier year KES 9,000,000,000 1/ })).toBeVisible();
  await expect(table.getByRole('row', { name: /2029 Amount unavailable Count unavailable/ })).toBeVisible();
  await expect(table.getByRole('row', { name: /2030 KES 0 0/ })).toBeVisible();
  await expect(table.getByRole('row', { name: /2031 Signed amount KES -300 2/ })).toBeVisible();
});

test('shows the largest reported year without asserting a five-year horizon when the snapshot date is missing', async ({ page }) => {
  await page.route(endpoint, route => route.fulfill({ json: {
    ...maturities, source: { ...maturities.source, as_of: null }, coverage: { coverage_ratio: null },
  } }));
  await page.goto('/debt');
  const section = page.getByRole('region', { name: 'When it’s due' });
  await expect(section.getByText('Five-year window unavailable')).toBeVisible();
  await expect(section.getByText('largest amount shown · 2034')).toBeVisible();
  await expect(section.locator('li[data-signal=near]')).toHaveCount(0);
  await section.getByText('What’s included?', { exact: true }).click();
  await expect(section.getByText('Register snapshot date unavailable.')).toBeVisible();
  await expect(section.getByText(/published Treasury-bond stock covered by this register is unavailable/)).toBeVisible();
});

test('distinguishes a failed request and retry from withheld or empty register data', async ({ page }) => {
  let available = false;
  await page.route(endpoint, route => available
    ? route.fulfill({ json: { status: 'unavailable', reason: 'all_rows_withheld_by_gate', withheld_by_gate: { count: 4 }, ladder: [] } })
    : route.fulfill({ status: 503, json: { detail: 'Fixture service unavailable' } }));
  await page.goto('/debt');
  const section = page.getByRole('region', { name: 'When it’s due' });
  await expect(section.getByText('The Treasury bond maturity profile could not be loaded.')).toBeVisible();
  available = true;
  await section.getByRole('button', { name: 'Try again' }).click();
  await expect(section.getByText('All stored Treasury bond records were withheld from publication.')).toBeVisible();
  await expect(section.getByText('4 stored bond records were withheld by publication checks.')).toBeVisible();
  await expect(section.getByRole('button', { name: 'Try again' })).toHaveCount(0);
});

test('identifies an empty successful response without a zero debt claim', async ({ page }) => {
  await page.route(endpoint, route => route.fulfill({ json: { ...maturities, ladder: [] } }));
  await page.goto('/debt');
  const section = page.getByRole('region', { name: 'When it’s due' });
  await expect(section.getByText('The register returned no dated Treasury bond amounts.')).toBeVisible();
  await expect(section.getByText(/KES 0/)).toHaveCount(0);
});
