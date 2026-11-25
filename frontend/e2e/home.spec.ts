import { expect, test } from '@playwright/test';
import { waitForAppReady } from './utils/selectors';
import { syntheticDebtTimeline20261105 } from '../test/fixtures/deploymentDebt20261105';

test.describe('Home debt timeline', () => {
  test.use({ hasTouch: true, viewport: { width: 360, height: 780 } });

  test('aligns the plots, reads a tapped year, and exposes the gaps in a table', async ({ page }) => {
    const latest = syntheticDebtTimeline20261105(65.9);
    const previous = syntheticDebtTimeline20261105(50);
    previous.year = 2023;
    previous.period.stock_as_of_month = '2023-12';
    previous.period.gdp_calendar_year = 2023;
    previous.qualifications.total.locator.cell = '2023-12 / total';
    previous.qualifications.gdp.locator.date = '2023';
    for (const source of Object.values(previous.qualifications)) source.identity.period = '2023';
    await page.clock.setFixedTime(new Date(Date.now() + 2 * 60 * 60 * 1000));
    await page.route('**/api/v1/debt/timeline', route => route.fulfill({
      json: { status: 'success', timeline: [previous, latest] },
    }));
    await page.goto('/');
    const charts = page.locator('[data-home-debt-charts]');
    const nominal = charts.getByRole('figure', { name: 'Debt in shillings' });
    const ratio = charts.getByRole('figure', { name: 'Debt as a share of GDP' });
    const plot = nominal.locator('[data-debt-plot-target]');
    const current = charts.locator('[data-home-debt-readout]');
    const year = charts.getByRole('combobox', { name: 'Choose a year' });
    await expect(year.locator('option')).toHaveText(['2023', '2024', '2025']);
    await expect(ratio.locator('[data-debt-point="2025"]')).toHaveCount(1);
    await expect(nominal.locator('[data-debt-line-segment]')).toHaveCount(2);
    await expect(ratio.locator('[data-debt-line-segment]')).toHaveCount(2);

    const bounds = (await plot.boundingBox())!;
    await plot.tap({ position: { x: bounds.width / 2, y: bounds.height / 2 } });
    await expect(current.getByText('2024')).toBeVisible();
    await expect(current.getByText('Unavailable', { exact: true })).toHaveCount(4);
    expect((await year.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    await year.focus();
    // Native select keys differ on WebKit. Selecting via the focused control
    // exercises the same change path without tapping a plot.
    await year.selectOption('2023');
    await expect(year).toBeFocused();
    await expect(current).toContainText('Central Bank debt stock as of 2023-12 · World Bank GDP for 2023');
    await expect(current.getByText('50%', { exact: true })).toBeVisible();
    await charts.getByText('Debt figures by year', { exact: true }).first().press('Enter');
    const table = charts.getByRole('table', { name: 'Debt figures by year' });
    await expect(table.getByRole('row').filter({ has: page.getByRole('rowheader', { name: '2023', exact: true }) })).toContainText('KES 4.00T');
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBe(360);
  });

  test('shows nominal debt when a legacy timeline lacks any matched period', async ({ page }) => {
    const { period, ...legacy } = syntheticDebtTimeline20261105(65.9);
    expect(period.stock_as_of_month).toBe('2025-12');
    await page.clock.setFixedTime(new Date(Date.now() + 2 * 60 * 60 * 1000));
    await page.route('**/api/v1/debt/timeline', route => route.fulfill({
      json: { status: 'success', timeline: [legacy] },
    }));
    await page.goto('/');
    const charts = page.locator('[data-home-debt-charts]');
    await expect(charts.getByRole('figure', { name: 'Debt in shillings' }).locator('[data-debt-point="2025"]')).toHaveCount(1);
    const ratio = charts.getByRole('figure', { name: 'Debt as a share of GDP' });
    await expect(ratio.getByText(/could not be verified together/)).toBeVisible();
    await expect(ratio.locator('[data-debt-point]')).toHaveCount(0);
  });
});

test('the Home questions offer keyboard navigation to the existing public pages', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 780 });
  await page.goto('/');
  await waitForAppReady(page);
  await expect(page.getByRole('heading', { name: 'Where does Kenya’s money go?', level: 1 })).toBeVisible();
  await expect(page.locator('meta[name="description"]')).toHaveAttribute('content', /from official records\./);

  const topics = page.getByRole('navigation', { name: 'What do you want to know?' });
  const destinations = [
    ['How much does Kenya owe?', '/debt'],
    ['Where do my taxes go?', '/budget'],
    ['How is my county doing?', '/counties'],
    ['What did the Auditor-General find?', '/audits'],
  ] as const;
  await expect(topics.getByRole('link')).toHaveCount(destinations.length);
  for (const [question, href] of destinations) {
    await expect(topics.getByRole('link', { name: question, exact: true })).toHaveAttribute('href', href);
  }

  const hero = page.getByRole('region', { name: 'Where does Kenya’s money go?' });
  await expect(hero).toContainText('Data from the Central Bank, Treasury, Auditor-General and Controller of Budget.');
  const countySearch = hero.getByRole('combobox', { name: 'Find your county' });
  await expect(countySearch).toBeEnabled();
  const firstTopic = topics.getByRole('link', { name: destinations[0][0] });
  await firstTopic.focus();
  for (const [question] of destinations) {
    await expect(topics.getByRole('link', { name: question })).toBeFocused();
    await page.keyboard.press('Tab');
  }
  await expect(countySearch).toBeFocused();
  await page.keyboard.press('Tab');
  const sources = hero.getByRole('link', { name: 'Data & sources' });
  await expect(sources).toBeFocused();
  await expect(sources).toHaveAttribute('href', '/sources');
  await page.keyboard.press('Shift+Tab');
  await page.keyboard.press('Shift+Tab');
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/\/audits\/?$/);
  await expect(page.getByRole('heading', { level: 1, name: 'Audit Findings' })).toBeVisible();
});

test('Home county search navigates a list and opens the selected county with the keyboard', async ({ page }) => {
  await page.goto('/');
  const search = page.getByRole('combobox', { name: 'Find your county' });
  const suggestions = page.getByRole('listbox', { name: 'Find your county' });

  await search.fill('Kis');
  await expect(suggestions.getByRole('option')).toHaveText(['Kisii', 'Kisumu']);
  await search.press('ArrowDown');
  await expect(suggestions.getByRole('option', { name: 'Kisii', selected: true })).toBeVisible();
  await search.press('ArrowDown');
  const kisumu = suggestions.getByRole('option', { name: 'Kisumu', selected: true });
  await expect(kisumu).toBeVisible();
  await expect(search).toHaveAttribute('aria-activedescendant', (await kisumu.getAttribute('id'))!);
  await search.press('Escape');
  await expect(search).toBeFocused();
  await expect(search).toHaveValue('Kis');
  await expect(search).toHaveAttribute('aria-expanded', 'false');
  await expect(search).not.toHaveAttribute('aria-activedescendant');
  await expect(suggestions).toHaveCount(0);

  await search.press('ArrowUp');
  await expect(kisumu).toBeVisible();
  await search.press('Tab');
  await expect(search).not.toBeFocused();
  await expect(suggestions).toHaveCount(0);

  await page.getByRole('button', { name: 'Clear county search' }).press('Enter');
  await expect(search).toBeFocused();
  await expect(search).toHaveValue('');

  await search.fill('Kis');
  await search.press('ArrowUp');
  await search.press('Enter');
  await expect(page).toHaveURL(/\/counties\/kisumu\/?$/);
  await expect(page.getByRole('heading', { level: 1, name: 'Kisumu County' })).toBeVisible();

  await page.goto('/');
  await search.fill('murang’a county');
  await expect(suggestions.getByRole('option', { name: "Murang'a" }))
    .toHaveAttribute('href', '/counties/Murang%27a');
  await search.press('Enter');
  await expect(page).toHaveURL(/\/counties\/Murang%27a\/?$/);
  await expect(page.getByRole('heading', { level: 1, name: "Murang'a County" })).toBeVisible();
});

test.describe('Home county search on touch screens', () => {
  test.use({ hasTouch: true, viewport: { width: 360, height: 780 } });

  test('dismisses suggestions, clears a no-match query, and opens a multiword county', async ({ page }) => {
    await page.goto('/');
    const search = page.getByRole('combobox', { name: 'Find your county' });
    const suggestions = page.getByRole('listbox', { name: 'Find your county' });
    const clear = page.getByRole('button', { name: 'Clear county search' });

    await search.tap();
    await search.fill('homa');
    await expect(suggestions.getByRole('option', { name: 'Homa Bay' })).toBeVisible();
    await page.getByRole('heading', { level: 1, name: 'Where does Kenya’s money go?' }).tap();
    await expect(search).toHaveAttribute('aria-expanded', 'false');
    await expect(search).toHaveValue('homa');

    await search.tap();
    await search.fill('zzzz');
    await expect(page.getByRole('status').filter({ hasText: 'No counties found.' })).toBeVisible();
    await expect(suggestions).toHaveCount(0);
    await clear.tap();
    await expect(search).toHaveValue('');
    await expect(search).toBeFocused();
    await expect(clear).toHaveCount(0);

    await search.fill('HOMA-BAY');
    const county = suggestions.getByRole('option', { name: 'Homa Bay' });
    await expect(county).toHaveAttribute('href', '/counties/homa-bay');
    await county.tap();
    await expect(page).toHaveURL(/\/counties\/homa-bay\/?$/);
    await expect(page.getByRole('heading', { level: 1, name: 'Homa Bay County' })).toBeVisible();
  });
});

test('home dashboard renders and allows county selection via map', async ({ page }) => {
  await page.goto('/');
  await waitForAppReady(page);
  const map = page.locator('#home-map');
  await map.scrollIntoViewIfNeeded();
  await expect(map.locator('path.rsm-geography')).toHaveCount(47);
  await map.locator('path.rsm-geography').first().click();
  await expect(map.getByRole('link', { name: 'Explore Baringo', exact: true })).toBeVisible();
  await expect(map).toContainText('KES 10.0B');
  await expect(map).toContainText('60.0%');
  await expect(map).toContainText('Synthetic browser finding');
});

test('the Home loan card displays full creditor names at 360px', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 780 });
  // Age the SSR query past its one-hour stale time so this test can supply its own loan rows.
  await page.clock.setFixedTime(Date.now() + 2 * 60 * 60 * 1000);
  const creditors = [
    ['Bilateral (Finland)', 'Finland'],
    [
      'Multilateral (International Bank for Reconstruction and Development (IBRD)\u00a0\u00a0)',
      'International Bank for Reconstruction and Development (IBRD)',
    ],
    ['Standard Chartered Syndicated Loan', 'Standard Chartered Syndicated Loan'],
  ];
  await page.route('**/api/v1/debt/loans', route => route.fulfill({ json: {
    loans: creditors.map(([lender], index) => ({
      lender,
      lender_type: ['external_bilateral', 'external_multilateral', 'external_commercial'][index],
      outstanding_numeric: (index + 1) * 1_000_000_000,
      interest_rate_pct: null,
      annual_service_cost: null,
    })),
    annual_debt_service: { value_kes: null, absent_reason: 'No figure in this fixture' },
    source: 'Synthetic loan register',
    total_loans: creditors.length,
    total_outstanding: 6_000_000_000,
  } }));

  await page.goto('/');
  await waitForAppReady(page);
  for (const [, displayName] of creditors) {
    const name = page.getByText(displayName, { exact: true });
    await expect(name).toBeVisible();
    await expect(name).toHaveCSS('text-overflow', 'clip');
    const { scrollWidth, clientWidth } = await name.evaluate(element => ({
      scrollWidth: element.scrollWidth,
      clientWidth: element.clientWidth,
    }));
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth);
  }
});
