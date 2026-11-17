import { expect, test } from '@playwright/test';
import { waitForAppReady } from './utils/selectors';

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
  const firstTopic = topics.getByRole('link', { name: destinations[0][0] });
  await firstTopic.focus();
  for (const [question] of destinations) {
    await expect(topics.getByRole('link', { name: question })).toBeFocused();
    await page.keyboard.press('Tab');
  }
  const sources = hero.getByRole('link', { name: 'Data & sources' });
  await expect(sources).toBeFocused();
  await expect(sources).toHaveAttribute('href', '/sources');
  await page.keyboard.press('Shift+Tab');
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/\/audits\/?$/);
  await expect(page.getByRole('heading', { level: 1, name: 'Audit Findings' })).toBeVisible();
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
