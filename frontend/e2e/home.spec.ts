import { expect, test } from '@playwright/test';
import { waitForAppReady } from './utils/selectors';

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
