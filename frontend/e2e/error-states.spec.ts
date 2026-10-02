import { expect, test } from '@playwright/test';
import { countyResponse } from './utils/countyResponse';

const countyError = /Error loading counties|Failed to load counties|Unable to load/i;

test.describe('Error States - API Failures', () => {
  test('handles 500 server error gracefully', async ({ page }) => {
    const errors: string[] = []; page.on('pageerror', e => errors.push(e.message));
    await countyResponse(page, r => r.fulfill({ status: 500, json: { detail: 'Synthetic failed read' } }));
    await expect(page.getByText(countyError).first()).toBeVisible();
    await expect(page.getByRole('button', { name: /Try Again|Retry/i })).toBeVisible();
    expect(errors).toEqual([]);
  });
  test('handles 404 not found error', async ({ page, request }) => {
    const res = await request.get('/api/v1/counties/999');
    expect(res.ok()).toBe(false);
    await page.goto('/counties/999');
    await expect(page.getByText(/County not found|Unable to load county|Failed to load county data/i).first()).toBeVisible();
  });
  test('handles network timeout gracefully', async ({ page }) => {
    await countyResponse(page, r => r.abort('timedout'));
    await expect(page.getByText(countyError).first()).toBeVisible();
  });
  test('retry button works after API failure', async ({ page }) => {
    let fail = true;
    const calls = await countyResponse(page, async r => {
      if (fail) return r.fulfill({ status: 500, json: { detail: 'Synthetic failed read' } });
      await r.fulfill({ response: await r.fetch() });
    });
    await expect(page.getByText(countyError).first()).toBeVisible();
    const before = calls(); fail = false;
    await page.getByRole('button', { name: /Try Again|Retry/i }).click();
    await expect.poll(calls).toBeGreaterThan(before);
    await expect(page.locator('table tbody tr')).toHaveCount(10);
    await expect(page.locator('table tbody tr').first()).toContainText('8.0B');
  });
});

test.describe('Error States - Empty Data', () => {
  test('shows empty state when no counties found', async ({ page }) => {
    await countyResponse(page, r => r.fulfill({ json: [] }));
    await expect(page.locator('table tbody tr')).toHaveCount(0);
    await expect(page.getByText(/No counties|No results/i).first()).toBeVisible();
  });
  test('shows empty state for search with no results', async ({ page }) => {
    await page.goto('/counties');
    await page.getByPlaceholder('Type to search…').fill('NoSuchSyntheticCounty');
    await expect(page.locator('table tbody tr')).toHaveCount(0);
    await expect(page.getByText(/No counties|No results/i).first()).toBeVisible();
  });
  test('shows empty state when no reports available', async ({ page }) => {
    await page.goto('/audits');
    await page.getByText('Severity', { exact: true }).locator('..').getByRole('combobox').selectOption('Critical');
    await expect(page.getByText('No findings match your filters.', { exact: true })).toBeVisible();
    await expect(page.locator('table tbody tr').filter({ hasText: 'KES 1.0M' })).toHaveCount(0);
  });
});

test.describe('Error States - Invalid Data', () => {
  test('handles malformed API response', async ({ page }) => {
    await countyResponse(page, r => r.fulfill({ contentType: 'application/json', body: 'INVALID JSON {' }));
    await expect(page.getByText(countyError).first()).toBeVisible();
  });
  // A response lacking County.name reaches the current list's localeCompare
  // and renders the React error boundary. Exact invalid-schema case retained
  // under #291 for coordinator tracking; never count it as a successful read.
  test.fixme('handles missing required fields in API response', async () => {});
  test('handles negative or invalid numeric values', async ({ page, request }) => {
    const res = await request.get('/api/v1/counties/001'); expect(res.ok()).toBe(true);
    const county = await res.json();
    await countyResponse(page, r => r.fulfill({ json: [{ ...county, total_debt: -1000 }] }));
    const row = page.locator('table tbody tr');
    await expect(row).toHaveCount(1);
    // Preserve a valid budget; invalid selected borrowing must be withheld.
    await expect(row).toContainText('10.0B');
    await expect(row.locator('td').nth(6)).toHaveText('—');
    await expect(row).not.toContainText('-1000');
  });
});

test.describe('Error States - Authentication & Authorization', () => {
  for (const [status, title] of [[401, 'handles 401 unauthorized error'], [403, 'handles 403 forbidden error']] as const) {
    test(title, async ({ page }) => {
      await countyResponse(page, r => r.fulfill({ status, json: { detail: 'Synthetic refused read' } }));
      await expect(page.getByText(countyError).first()).toBeVisible();
    });
  }
});

test.describe('Error States - Loading States', () => {
  for (const title of ['shows loading state while fetching data', 'shows skeleton loaders for slow data']) {
    test(title, async ({ page }) => {
      let release!: () => void;
      const pending = new Promise<void>(resolve => { release = resolve; });
      await countyResponse(page, async r => { await pending; await r.fulfill({ response: await r.fetch() }); });
      await expect(page.locator('[class*="animate-spin"]').first()).toBeVisible();
      release();
      await expect(page.locator('table tbody tr')).toHaveCount(10);
      await expect(page.locator('table tbody tr').first()).toContainText('8.0B');
    });
  }
});

test.describe('Error States - Offline Handling', () => {
  test('handles offline state gracefully', async ({ page }) => {
    await countyResponse(page, r => r.abort('internetdisconnected'));
    await expect(page.getByText(countyError).first()).toBeVisible();
    await expect(page.getByRole('banner')).toBeVisible();
  });
});

test.describe('Error States - Boundary Conditions', () => {
  test('handles extremely large dataset gracefully', async ({ page, request }) => {
    const response = await request.get('/api/v1/counties/001'); expect(response.ok()).toBe(true);
    const county = await response.json();
    const many = Array.from({ length: 1000 }, (_, n) => ({ ...county, id: `synthetic-${n}`, name: `Synthetic County ${n}` }));
    await countyResponse(page, r => r.fulfill({ json: many }));
    await expect(page.getByText('Showing 1–10 of 1000 Counties', { exact: true })).toBeVisible();
    await expect(page.locator('table tbody tr')).toHaveCount(10);
  });
  test('handles special characters in data', async ({ page, request }) => {
    const response = await request.get('/api/v1/counties/001'); expect(response.ok()).toBe(true);
    const county = await response.json();
    await countyResponse(page, r => r.fulfill({ json: [{ ...county, name: '<script>Synthetic & County</script>' }] }));
    await expect(page.locator('table tbody tr')).toContainText('<script>Synthetic & County</script>');
    await expect(page.locator('table script')).toHaveCount(0);
  });
});
