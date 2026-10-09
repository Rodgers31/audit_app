import { expect, type Page, type Route } from '@playwright/test';

// Initial county data is SSR-prefetched. Select a different period to exercise
// the browser response instead of silently testing the hydrated happy path.
export async function countyResponse(page: Page, handle: (route: Route) => Promise<void>) {
  await page.goto('/counties');
  await expect(page.getByRole('searchbox', { name: 'Search County', exact: true })).toBeVisible();
  let calls = 0;
  await page.route(url => url.pathname === '/api/v1/counties' && url.searchParams.get('fiscal_year') === 'FY2024/25', async route => {
    calls++;
    await handle(route);
  });
  await page.getByText('Year', { exact: true }).locator('..').getByRole('combobox').selectOption('FY2024/25');
  await expect.poll(() => calls).toBeGreaterThan(0);
  return () => calls;
}
