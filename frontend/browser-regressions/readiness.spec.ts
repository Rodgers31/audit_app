import { test, expect, type Page } from '@playwright/test';

declare global {
  interface Window { __batch12ReleaseStream: () => void; }
}

async function holdStreamPromotion(page: Page) {
  await page.addInitScript(() => {
    let promote: (...args: unknown[]) => unknown;
    let wrapper: (...args: unknown[]) => unknown;
    const pending: (() => unknown)[] = [];
    let released = false;
    Object.defineProperty(window, '$RV', {
      configurable: true,
      get: () => wrapper,
      set(callback) {
        promote = callback;
        wrapper = function (this: unknown, ...args: unknown[]) {
          const invoke = () => Reflect.apply(promote, this, args);
          if (released) return invoke();
          pending.push(invoke);
        };
      },
    });
    window.__batch12ReleaseStream = () => {
      released = true;
      pending.splice(0).forEach(invoke => invoke());
    };
  });
}

async function holdBootstrap(page: Page) {
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/_next/static/**/*.js', async route => {
    await pending;
    await route.continue();
  });
  return release;
}

test('county heading is available while bootstrap and stream promotion are pending', async ({ page }) => {
  await holdStreamPromotion(page);
  const releaseBootstrap = await holdBootstrap(page);
  try {
    await page.goto('/counties', { waitUntil: 'domcontentloaded' });
    await page.getByRole('banner').waitFor({ state: 'visible' });
    // Same immediate role query as the original accessibility smoke case.
    const headings = await page.getByRole('heading', { level: 1 }).all();
    expect(headings).toHaveLength(1);
  } finally {
    await page.evaluate(() => window.__batch12ReleaseStream());
    releaseBootstrap();
  }
  await page.waitForLoadState('load');
  await expect(page.getByRole('heading', { name: 'County Explorer', exact: true })).toBeVisible();
});

test('county row summary stays unique while stream promotion is pending', async ({ page }) => {
  await holdStreamPromotion(page);
  try {
    await page.goto('/counties');
    // Keep the original strict text locator, including hidden matches.
    await expect(page.getByText('Showing 1–10 of 47 Counties', { exact: true })).toBeVisible();
    await expect(page.locator('table tbody tr')).toHaveCount(10);
  } finally {
    await page.evaluate(() => window.__batch12ReleaseStream());
  }
});

test('fiscal selector waits for hydration before accepting a year change', async ({ page }) => {
  const releaseBootstrap = await holdBootstrap(page);
  try {
    await page.goto('/budget', { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('heading', { name: 'KES 180B approved for FY 2025/26' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'FY2024/25', exact: true })).toBeDisabled();
  } finally {
    releaseBootstrap();
  }
  await page.waitForLoadState('load');
  await page.getByRole('button', { name: 'FY2024/25', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'KES 150B approved for FY 2024/25' })).toBeVisible();
});
