import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { countyTabs, waitForAppReady } from './utils/selectors';

// The browser suite serves a production build. Refuse a missing/ambiguous
// manifest rather than reject an unrelated Promise or guess a chunk number.
function tabChunk(module: string): string {
  const manifest = JSON.parse(readFileSync(join(process.cwd(), '.next/react-loadable-manifest.json'), 'utf8'));
  const entries = Object.entries(manifest).filter(([key]) => key.includes(`tabs/${module}`));
  expect(entries).toHaveLength(1);
  const files = (entries[0][1] as { files: string[] }).files;
  expect(files.length).toBeGreaterThan(0);
  return files[files.length - 1];
}

for (const width of [375, 1280]) {
  for (const entry of ['shell', 'deep-link'] as const) {
    test(`county tab at ${width}px via ${entry} recovers rejected code without losing its period or history`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: 900 });
      const chunk = tabChunk('MoneyFlowTab');
      let reject = true;
      let rejected = 0;
      let moneyCalls = 0;
      page.on('request', request => {
        if (new URL(request.url()).pathname === '/api/v1/counties/001/money-flow') moneyCalls++;
      });
      await page.route(url => url.pathname.endsWith(chunk), route => {
        if (reject) { rejected++; return route.abort('failed'); }
        return route.continue();
      });
      await page.goto(entry === 'shell'
        ? '/counties/001?fy=FY2024%2F25&from=money'
        : '/counties/001?tab=money&fy=FY2024%2F25&from=money#recovery-anchor');
      await waitForAppReady(page);
      const historyLength = await page.evaluate(() => history.length);
      if (entry === 'shell') await countyTabs.followTheMoney(page).press('Enter');
      await expect.poll(() => rejected).toBe(1);
      const alert = page.getByRole('alert').filter({ hasText: 'Could not load this section.' });
      await expect(alert).toBeVisible();
      await expect(countyTabs.followTheMoney(page)).toHaveAttribute('aria-pressed', 'true');
      expect(moneyCalls).toBe(0);
      await expect(page.getByRole('status', { name: 'Loading tab content' })).toHaveCount(0);
      const reload = alert.getByRole('button', { name: 'Reload section', exact: true });
      await reload.focus();
      await expect(reload).toBeFocused();
      expect((await reload.boundingBox())!.height).toBeGreaterThanOrEqual(44);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await testInfo.attach('rejected-tab', { body: await alert.screenshot(), contentType: 'image/png' });

      // A new document must really request the chunk again. Resetting a boundary
      // alone rethrows the permanently rejected next/dynamic lazy payload.
      await reload.press('Enter');
      await expect.poll(() => rejected).toBe(2);
      await expect(alert).toBeVisible();
      expect(moneyCalls).toBe(0);
      await expect(page).toHaveURL(/tab=money/);
      expect(new URL(page.url()).searchParams.get('fy')).toBe('FY2024/25');
      expect(new URL(page.url()).searchParams.get('from')).toBe('money');
      if (entry === 'deep-link') expect(new URL(page.url()).hash).toBe('#recovery-anchor');
      expect(await page.evaluate(() => history.length)).toBe(historyLength);

      reject = false;
      await alert.getByRole('button', { name: 'Reload section', exact: true }).press('Enter');
      await expect(page.getByText(/procurement-encumbered/)).toBeVisible();
      expect(moneyCalls).toBeGreaterThan(0);
      await expect(page.getByRole('combobox', { name: 'Fiscal year', exact: true })).toHaveValue('FY2024/25');
      await expect(page.getByText('Budget Allocation', { exact: true }).locator('..')).toContainText('KES 8.00B');
      await expect(page.getByRole('link', { name: 'Synthetic CBIRR browser acceptance publication', exact: true }))
        .toHaveAttribute('href', 'https://example.invalid/auditgava-local-budget.pdf');
      await expect(alert).toHaveCount(0);
      if (entry === 'deep-link') expect(new URL(page.url()).hash).toBe('#recovery-anchor');
      expect(await page.evaluate(() => history.length)).toBe(historyLength);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.goto('/counties');
      await page.goBack();
      await expect(page).toHaveURL(/tab=money/);
      await expect(page.getByText(/procurement-encumbered/)).toBeVisible();
      await page.goForward();
      await expect(page).toHaveURL(/\/counties$/);
    });
  }
}
