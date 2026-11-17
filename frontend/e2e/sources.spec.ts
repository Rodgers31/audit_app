import { expect, test } from '@playwright/test';
import { pageShell } from './utils/selectors';

const title = 'Where the data comes from';
const researcher = 'For researchers: data health';

test.describe('/sources', () => {
  test('shows the indexed publisher before the collapsed researcher disclosure', async ({ page }) => {
    await page.goto('/sources');
    await expect(pageShell.h1(page)).toHaveText(title);
    const publishers = page.getByRole('region', { name: 'Publishers' });
    await expect(publishers.getByRole('heading', { name: 'Synthetic local fixture' })).toBeVisible();
    await expect(publishers).toContainText('Documents indexed · 2');
    await expect(publishers.getByRole('link')).toHaveCount(0);
    await expect(page.locator('details').filter({ hasText: researcher })).not.toHaveAttribute('open', '');
    await expect(page.getByText('Document inventory', { exact: true })).toHaveCount(0);
  });

  test('opens researcher data health by keyboard and recovers from a failed health read', async ({ page }) => {
    await page.route('**/api/v1/sources/summary', (route) => route.fulfill({ json: {
      sources: [{
        publisher: 'Controller of Budget', website: 'https://cob.go.ke',
        document_count: 6, downloaded_documents: 0, extracted_documents: 0,
        last_fetched: null, doc_types: { report: 6 },
      }],
      total_documents: 6,
    } }));
    await page.route('**/api/v1/data/freshness', (route) => route.fulfill({
      status: 500, json: { detail: 'Synthetic freshness failure' },
    }));
    let healthRequests = 0;
    await page.route('**/api/v1/provenance/health', (route) => {
      healthRequests++;
      if (healthRequests === 1) return route.fulfill({ status: 500, json: { detail: 'Synthetic health failure' } });
      return route.fulfill({ json: { tables: [
        {
          table: 'county_data', label: 'County data', status: 'stale',
          row_count: 47, attribution_status: 'unresolved', unresolved_source_rows: 47,
          age_days: 72, stale_after_days: 50,
        },
        {
          table: 'audit_data', label: 'Audit data', status: 'empty',
          row_count: 0, attribution_status: 'empty',
        },
      ] } });
    });

    await page.setViewportSize({ width: 360, height: 800 });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto('/sources');
    const publishers = page.getByRole('region', { name: 'Publishers' });
    const publisherLink = publishers.getByRole('link', { name: 'Controller of Budget', exact: true });
    const summary = page.locator('summary').filter({ hasText: researcher });
    const details = page.locator('details').filter({ has: summary });
    await expect(publisherLink).toHaveAttribute('href', 'https://cob.go.ke/');
    await expect(publishers).toContainText('County and national spending');
    await expect(publishers).not.toContainText('Latest recorded publication date');
    expect(healthRequests).toBe(0);

    await publisherLink.focus();
    await page.keyboard.press('Tab');
    await expect(summary).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(details).toHaveAttribute('open', '');
    await expect(details.getByRole('alert')).toHaveText('Data health could not be loaded.');
    await expect(summary).toBeFocused();
    await details.getByRole('button', { name: 'Try again' }).click();
    await expect(details.getByText('Not yet linked to a source document')).toBeVisible();
    await expect(details.getByText('47 rows without resolved lineage')).toBeVisible();
    await expect(details.getByText('Stale after 50 days')).toBeVisible();
    await expect(details.getByText('0 rows', { exact: true })).toBeVisible();
    await expect(details.getByText('6 registered · 0 downloaded · 0 extracted')).toBeVisible();
    await expect(publisherLink).toBeVisible();

    await summary.focus();
    await page.keyboard.press('Space');
    await expect(details).not.toHaveAttribute('open', '');
    await expect(details.getByText('Not yet linked to a source document')).toBeHidden();
    expect(healthRequests).toBe(2);
  });
});
