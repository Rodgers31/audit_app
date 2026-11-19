import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { countyTabs, waitForAppReady } from './utils/selectors';

test.beforeEach(async ({ page }) => {
  await page.route(url => !['127.0.0.1', 'localhost'].includes(url.hostname), route => route.abort());
});

function moneyChunk(): string {
  const manifest = JSON.parse(readFileSync(join(process.cwd(), '.next/react-loadable-manifest.json'), 'utf8'));
  const entries = Object.entries(manifest).filter(([key]) => key.includes('tabs/MoneyFlowTab'));
  expect(entries).toHaveLength(1);
  const files = (entries[0][1] as { files: string[] }).files;
  expect(files.length).toBeGreaterThan(0);
  return files[files.length - 1];
}

for (const width of [375, 1280]) {
  test(`county tabs at ${width}px load data independently of a server navigation`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    const errors: string[] = [];
    const moneyResponses: { status: number; year: string | null }[] = [];
    let tabNavigations = 0;
    let chunkRequests = 0;
    let releaseChunk!: () => void;
    let releaseNavigation!: () => void;
    const chunkGate = new Promise<void>(resolve => { releaseChunk = resolve; });
    const navigationGate = new Promise<void>(resolve => { releaseNavigation = resolve; });
    page.on('pageerror', error => errors.push(error.message));
    page.on('response', response => {
      const url = new URL(response.url());
      if (url.pathname === '/api/v1/counties/001/money-flow') {
        moneyResponses.push({ status: response.status(), year: url.searchParams.get('year') });
      }
    });
    // Hold only a tab-induced Flight request. The initial document, actual
    // lazy chunk, and data reader remain real. A tab must work without this
    // server navigation, which is the source of the lost Flight render retry.
    await page.route(url => url.pathname === '/counties/001' &&
      url.searchParams.has('_rsc'), async route => {
      tabNavigations++;
      await navigationGate;
      await route.continue();
    });
    const chunk = moneyChunk();
    await page.route(url => url.pathname.endsWith(chunk), async route => {
      chunkRequests++;
      await chunkGate;
      await route.continue();
    });
    try {
      await page.goto('/counties/001?fy=FY2024%2F25&from=money&retained=one&retained=two#county-navigation-anchor');
      await waitForAppReady(page);
      const documentOrigin = await page.evaluate(() => performance.timeOrigin);
      const historyLength = await page.evaluate(() => history.length);
      expect(chunkRequests).toBe(0);
      await countyTabs.followTheMoney(page).press('Enter');
      await expect(countyTabs.followTheMoney(page)).toHaveAttribute('aria-selected', 'true');
      await expect(page.getByRole('status', { name: 'Loading tab content' })).toBeVisible();
      await expect.poll(() => chunkRequests).toBe(1);
      expect(moneyResponses).toEqual([]);
      releaseChunk();
      await expect(page.getByText(/Reported procurement commitments KES/).first()).toBeVisible();
      await expect(page.getByRole('combobox', { name: 'Fiscal year', exact: true })).toHaveValue('FY2024/25');
      await expect(page.getByRole('button', { name: /^Allocated KES/ })).toContainText('KES 8.00B');
      await page.getByRole('button', { name: 'Source: Synthetic CBIRR browser acceptance publication' }).click();
      await expect(page.getByRole('link', { name: 'Synthetic CBIRR browser acceptance publication', exact: true }))
        .toHaveAttribute('href', 'https://example.invalid/auditgava-local-budget.pdf');
      await page.keyboard.press('Escape');
      expect(moneyResponses).toContainEqual({ status: 200, year: 'FY2024/25' });
      expect(tabNavigations).toBe(0);
      expect(await page.evaluate(() => performance.timeOrigin)).toBe(documentOrigin);
      const url = new URL(page.url());
      expect(url.searchParams.get('tab')).toBe('money');
      expect(url.searchParams.get('fy')).toBe('FY2024/25');
      expect(url.searchParams.get('from')).toBe('money');
      expect(url.searchParams.getAll('retained')).toEqual(['one', 'two']);
      expect(url.hash).toBe('#county-navigation-anchor');
      expect(await page.evaluate(() => history.length)).toBe(historyLength);

      await page.reload();
      await expect(page.getByText(/Reported procurement commitments KES/).first()).toBeVisible();
      await expect(countyTabs.followTheMoney(page)).toHaveAttribute('aria-selected', 'true');
      await countyTabs.overview(page).press('Enter');
      await expect(countyTabs.overview(page)).toHaveAttribute('aria-selected', 'true');
      expect(new URL(page.url()).searchParams.has('tab')).toBe(false);
      expect(new URL(page.url()).hash).toBe('#county-navigation-anchor');
      expect(await page.evaluate(() => history.length)).toBe(historyLength);
      expect(tabNavigations).toBe(0);
      expect(errors).toEqual([]);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    } finally {
      releaseChunk();
      releaseNavigation();
    }
  });

  test(`county tab at ${width}px follows restored query state`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/counties/001?tab=money&fy=FY2024%2F25#from-history');
    await expect(page.getByText(/Reported procurement commitments KES/).first()).toBeVisible();
    await page.evaluate(() => history.pushState(null, '', '/counties/001?tab=budget&fy=FY2024%2F25#from-history'));
    await expect(countyTabs.budgetDebt(page)).toHaveAttribute('aria-selected', 'true');
    await page.goBack();
    await expect(countyTabs.followTheMoney(page)).toHaveAttribute('aria-selected', 'true');
    await expect(page.getByText(/Reported procurement commitments KES/).first()).toBeVisible();
    expect(new URL(page.url()).searchParams.get('fy')).toBe('FY2024/25');
    expect(new URL(page.url()).hash).toBe('#from-history');
  });
}

test.describe('sticky county tabs', () => {
  test.use({ hasTouch: true, reducedMotion: 'reduce', viewport: { width: 360, height: 800 } });

  test('keeps the strip under the header and separates focus from selection', async ({ page }) => {
    await page.goto('/counties/001?fy=FY2024%2F25');
    const strip = page.getByRole('tablist', { name: 'Explore this county' });
    const sticky = strip.locator('..');
    const overview = countyTabs.overview(page);
    const budget = countyTabs.budgetDebt(page);
    const score = countyTabs.accountability(page);
    const tabBounds = await strip.getByRole('tab').evaluateAll((tabs) => tabs.map((tab) => {
      const { top, width, height } = tab.getBoundingClientRect();
      return { top, width, height };
    }));
    expect(tabBounds).toHaveLength(5);
    expect(new Set(tabBounds.map(({ top }) => top)).size).toBe(1);
    expect(tabBounds.every(({ width, height }) => width >= 44 && height >= 44)).toBe(true);
    await expect(sticky).toContainText('Nairobi County');
    await expect(sticky).toContainText('FY2024/25');

    const normalTop = await sticky.evaluate((element) => element.getBoundingClientRect().top);
    const headerBottom = (await page.getByRole('banner').boundingBox())!.height;
    expect(normalTop).toBeGreaterThan(headerBottom);
    await page.evaluate((top) => window.scrollTo(0, top + 240), normalTop);
    await expect.poll(async () => Math.abs((await sticky.boundingBox())!.y - headerBottom)).toBeLessThanOrEqual(1);

    await overview.focus();
    await page.keyboard.press('ArrowLeft');
    await expect(score).toBeFocused();
    await expect(overview).toHaveAttribute('aria-selected', 'true');
    expect(new URL(page.url()).searchParams.has('tab')).toBe(false);
    await page.keyboard.press('Home');
    await expect(overview).toBeFocused();
    await page.keyboard.press('ArrowRight');
    await page.keyboard.press('ArrowRight');
    await expect(budget).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(budget).toHaveAttribute('aria-selected', 'true');
    const budgetPanel = page.getByRole('tabpanel', { name: 'Budget' });
    await expect(budgetPanel).toHaveAttribute('aria-labelledby', (await budget.getAttribute('id'))!);
    await expect(sticky.locator('..').locator(':scope > [role=tabpanel]:not([hidden])')).toHaveCount(1);
    await page.keyboard.press('Tab');
    await expect(budgetPanel).toBeFocused();

    await score.tap();
    await expect(score).toHaveAttribute('aria-selected', 'true');
    await expect(page.getByRole('tabpanel', { name: 'Score' })).toBeVisible();
    expect(new URL(page.url()).searchParams.get('tab')).toBe('accountability');
    expect(new URL(page.url()).searchParams.get('fy')).toBe('FY2024/25');
  });
});
