/**
 * Data Sources page (/sources)
 */
import { expect, test } from '@playwright/test';
import { pageShell, waitForAppReady } from './utils/selectors';

test.describe('/sources', () => {
  test('shows documents-indexed total + publishing-agencies count', async ({ page }) => {
    await page.goto('/sources');
    await waitForAppReady(page);

    await expect(pageShell.h1(page)).toContainText(
      /Where the data comes from|Vyanzo vya Data/i
    );
    await expect(page.getByText(/Documents indexed|Nyaraka zilizopangwa/i)).toBeVisible();
    await expect(page.getByText(/Publishing agencies|Mashirika/i)).toBeVisible();
  });

  test('lists the Controller of Budget agency card', async ({ page }) => {
    await page.goto('/sources');
    await waitForAppReady(page);

    const cob = page.getByRole('article').filter({ hasText: /Controller of Budget|COB/ }).first();
    await expect(cob).toBeVisible({ timeout: 15_000 });
    await expect(cob).toContainText(/COB/);
  });

  test('each agency card with a website exposes an external Visit-site link', async ({ page }) => {
    await page.goto('/sources');
    await waitForAppReady(page);

    const visit = page.getByRole('link', { name: /Visit site/i }).first();
    await expect(visit).toBeVisible();
    await expect(visit).toHaveAttribute('target', '_blank');
    await expect(visit).toHaveAttribute('rel', /noopener/);
    const href = await visit.getAttribute('href');
    expect(href).toMatch(/^https?:\/\//);
  });
});
