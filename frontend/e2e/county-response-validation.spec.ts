import { expect, test, type Page, type Route } from '@playwright/test';
import { countyResponse } from './utils/countyResponse';

const listError = /Error loading counties|Failed to load counties|Unable to load/i;
const detailError = /Failed to load county data/i;
const invalidFields = [
  ['absent', undefined], ['null', null], ['number', 7], ['boolean', false],
  ['object', {}], ['array', []], ['empty', ''], ['whitespace', ' \t\n '],
] as const;

// Use Next's supported History API integration to change the consumed query
// after SSR hydration. A route registered before goto alone would only test
// the valid prefetched response and miss the hostile browser response.
async function detailResponse(page: Page, handle: (route: Route) => Promise<void>) {
  await page.goto('/counties/001');
  await expect(page.getByRole('heading', { name: 'Nairobi County', exact: true })).toBeVisible();
  let calls = 0;
  await page.route(url => url.pathname === '/api/v1/counties/001/comprehensive' && url.searchParams.get('fiscal_year') === 'FY2024/25', async route => {
    calls++;
    await handle(route);
  });
  await page.evaluate(() => window.history.pushState(null, '', '/counties/001?fy=FY2024%2F25'));
  await expect.poll(() => calls).toBeGreaterThan(0);
}

for (const surface of ['list', 'detail'] as const) {
  const consume = surface === 'list' ? countyResponse : detailResponse;
  const controlledError = async (page: Page, errors: string[]) => {
    await expect(page.getByText(surface === 'list' ? listError : detailError).first()).toBeVisible();
    await expect(page.getByRole('banner')).toBeVisible();
    await expect(page.locator('table tbody tr')).toHaveCount(0);
    await expect(page.getByText(/Application error: a client-side exception/)).toHaveCount(0);
    expect(errors).toEqual([]);
  };

  for (const field of ['id', 'name'] as const) {
    for (const [label, value] of invalidFields) {
      test(`${surface}: invalid ${field} (${label}) shows a controlled error`, async ({ page }) => {
        const errors: string[] = [];
        page.on('pageerror', e => errors.push(e.message));
        await consume(page, async route => {
          const response = await route.fetch();
          expect(response.status()).toBe(200);
          const data = await response.json();
          if (surface === 'list') expect(data).toHaveLength(47);
          const county = surface === 'list' ? data[0] : data;
          if (value === undefined) delete county[field];
          else county[field] = value;
          await route.fulfill({ json: data });
        });
        await controlledError(page, errors);
      });
    }
  }

  for (const [label, data] of [['null', null], ['object', {}], ['string', 'garbage'], ['number', 42], ['boolean', false]] as const) {
    test(`${surface}: malformed container (${label}) shows a controlled error`, async ({ page }) => {
      const errors: string[] = [];
      page.on('pageerror', e => errors.push(e.message));
      await consume(page, route => route.fulfill({ json: data }));
      await controlledError(page, errors);
    });
  }
}

test('normal 47-county list and legacy 001/047 detail routes remain usable', async ({ page, request }) => {
  const errors: string[] = [];
  page.on('pageerror', e => errors.push(e.message));
  const response = await request.get('/api/v1/counties');
  expect(response.status()).toBe(200);
  const counties = await response.json();
  expect(counties).toHaveLength(47);
  expect(counties.find((c: { id: string }) => c.id === '001').name).toBe('Nairobi');
  expect(counties.find((c: { id: string }) => c.id === '047').name).toBe('Mombasa');
  await page.goto('/counties');
  await expect(page.getByText('Showing 1–10 of 47 Counties', { exact: true })).toBeVisible();
  await expect(page.locator('table tbody tr')).toHaveCount(10);
  for (const [id, name] of [['001', 'Nairobi'], ['047', 'Mombasa']]) {
    await page.goto(`/counties/${id}`);
    await expect(page.getByRole('heading', { name: `${name} County`, exact: true })).toBeVisible();
  }
  expect(errors).toEqual([]);
});

// Age the hydrated comparison entry beyond its hour of freshness to exercise
// the actual client refetch. Timers keep running; only the browser's clock
// moves. SSR rejection also runs through the real server component in Jest.
for (const width of [390, 1280]) {
  test(`comparison malformed response can recover by keyboard at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    await page.clock.setFixedTime(new Date(Date.now() + 3_600_001));
    const errors: string[] = [];
    page.on('pageerror', e => errors.push(e.message));
    let fail = true;
    let calls = 0;
    await page.route(url => url.pathname === '/api/v1/counties' && url.searchParams.get('limit') === '50', async route => {
      calls++;
      const response = await route.fetch();
      expect(response.status()).toBe(200);
      const counties = await response.json();
      expect(counties).toHaveLength(47);
      if (fail) delete counties[0].name;
      await route.fulfill({ json: counties });
    });
    await page.goto('/counties/compare');
    await expect.poll(() => calls).toBeGreaterThan(0);
    await expect(page.getByRole('alert').filter({ hasText: listError })).toBeVisible();
    await expect(page.getByRole('combobox')).toHaveCount(0);
    const retry = page.getByRole('button', { name: /Try Again|Retry/i });
    await retry.focus();
    await expect(retry).toBeFocused();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    fail = false;
    const before = calls;
    await page.keyboard.press('Enter');
    await expect.poll(() => calls).toBeGreaterThan(before);
    await expect(page.getByRole('alert').filter({ hasText: listError })).toHaveCount(0);
    await expect(page.getByRole('combobox')).toHaveCount(2);
    await expect(page.getByRole('combobox').first().locator('option')).toHaveCount(48);
    expect(errors).toEqual([]);
  });
}
