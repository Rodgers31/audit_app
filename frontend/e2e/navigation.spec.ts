/**
 * Top-level navigation.
 *
 * Validates the global header + footer + language-switcher behaviour
 * that every page shares. Kept deliberately light on data assertions
 * so these tests can run against a live backend *or* a mocked one —
 * selectors target the scaffolding, not the rendered data.
 *
 * Replaces the pre-v1.1 spec that asserted a `/reports` route (never
 * shipped) and used CSS-attribute selectors that break when i18n flips
 * the nav labels.
 */
import { expect, test } from '@playwright/test';
import { langSwitcher, nav, waitForAppReady } from './utils/selectors';

test.describe('Navigation — desktop header', () => {
  test('header renders with all primary links', async ({ page }) => {
    await page.goto('/');
    await waitForAppReady(page);

    await expect(nav.debt(page)).toBeVisible();
    await expect(nav.budget(page)).toBeVisible();
    await expect(nav.counties(page)).toBeVisible();
    await expect(nav.transparency(page)).toBeVisible();
    await expect(nav.learn(page)).toBeVisible();
  });

  test('clicking each nav link routes correctly', async ({ page }) => {
    const routes: { linkKey: 'debt' | 'budget' | 'counties' | 'transparency' | 'learn'; urlPattern: RegExp }[] = [
      { linkKey: 'debt', urlPattern: /\/debt\/?$/ },
      { linkKey: 'budget', urlPattern: /\/budget\/?$/ },
      { linkKey: 'counties', urlPattern: /\/counties\/?$/ },
      { linkKey: 'transparency', urlPattern: /\/transparency\/?$/ },
      { linkKey: 'learn', urlPattern: /\/learn\/?$/ },
    ];

    await page.goto('/');
    await waitForAppReady(page);

    for (const { linkKey, urlPattern } of routes) {
      await nav[linkKey](page).click();
      await page.waitForURL(urlPattern, { timeout: 15_000 });
      await expect(page).toHaveURL(urlPattern);
    }
  });

  test('logo link returns to /', async ({ page }) => {
    await page.goto('/counties');
    await waitForAppReady(page);

    const logo = nav.home(page);
    await logo.click();
    await expect(page).toHaveURL(/\/$/);
  });
});

test.describe('Navigation — mobile menu', () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test('mobile menu toggle opens + reveals all routes', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    await expect(nav.mobileMenuToggle(page)).toBeVisible();

    await nav.mobileMenuToggle(page).click();

    // The open state should surface the close-label and all routes.
    await expect(
      page.getByRole('dialog').getByRole('button', { name: /close navigation menu|Funga menyu/i })
    ).toBeVisible();
    // Each primary route appears somewhere in the overlay.
    await expect(page.getByRole('link', { name: /National Debt|Deni la Taifa/i }).last()).toBeVisible();
    await expect(page.getByRole('link', { name: /Counties|Kaunti/i }).last()).toBeVisible();
  });
});

test.describe('Language switcher', () => {
  test('the language control opens with English active', async ({ page }) => {
    // Ensure a clean localStorage for a deterministic starting state.
    await page.addInitScript(() => window.localStorage.removeItem('auditgava-lang'));
    await page.goto('/');
    await waitForAppReady(page);

    await page.locator('header summary').filter({ hasText: /^Language$/ }).click();
    await expect(langSwitcher.root(page)).toBeVisible();
    await expect(langSwitcher.en(page)).toBeChecked();
  });

  test('switching to SW re-labels nav to Kiswahili', async ({ page }) => {
    await page.goto('/');
    await waitForAppReady(page);

    await page.locator('header summary').filter({ hasText: /^Language$/ }).click();
    await langSwitcher.sw(page).check();
    await expect(langSwitcher.sw(page)).toBeChecked();

    await expect(
      page.getByRole('link', { name: /^Deni la taifa$/ }).first()
    ).toBeVisible({ timeout: 5_000 });
    await expect(
      page.getByRole('link', { name: /^Bajeti$/ }).first()
    ).toBeVisible();
  });

  test('switching to plain English keeps the main routes', async ({ page }) => {
    await page.goto('/');
    await waitForAppReady(page);

    await page.locator('header summary').filter({ hasText: /^Language$/ }).click();
    await langSwitcher.plain(page).check();
    await expect(langSwitcher.plain(page)).toBeChecked();
    await expect(
      page.getByRole('link', { name: /^National debt$/ }).first()
    ).toBeVisible();
  });

  test('language choice persists across reload', async ({ page }) => {
    await page.goto('/');
    await waitForAppReady(page);

    await page.locator('header summary').filter({ hasText: /^Language$/ }).click();
    await langSwitcher.plain(page).check();
    await expect(langSwitcher.plain(page)).toBeChecked();

    await page.reload();
    await waitForAppReady(page);
    await page.locator('header summary').filter({ hasText: /^Language$/ }).click();
    await expect(langSwitcher.plain(page)).toBeChecked();
  });
});

test.describe('Footer', () => {
  test('renders with site name + current-year copyright', async ({ page }) => {
    await page.goto('/');
    await waitForAppReady(page);

    const footer = page.getByRole('contentinfo');
    await expect(footer).toBeVisible();
    await expect(footer).toContainText(/AuditGava/);
    await expect(footer).toContainText(/20\d{2}/);
  });
});


test('a missing page offers working county search and primary routes', async ({ page }) => {
  const response = await page.goto('/missing-foundation-test-page');
  expect(response?.status()).toBe(404);
  await expect(page).toHaveTitle(/We can’t find that page/);
  await page.getByRole('searchbox', { name: 'Search counties or glossary terms' }).fill('Bari');
  await expect(page.getByRole('link', { name: 'Baringo', exact: true })).toHaveAttribute('href', '/counties/baringo');
  await page.getByRole('searchbox', { name: 'Search counties or glossary terms' }).fill('muranga');
  const muranga = page.getByRole('link', { name: "Murang'a", exact: true });
  await expect(muranga).toHaveAttribute('href', '/counties/Murang%27a');
  await expect(page.getByRole('main').getByRole('link', { name: 'Audit findings' })).toHaveAttribute('href', '/audits');
  await muranga.click();
  await expect(page).toHaveURL(/\/counties\/Murang%27a\/?$/);
  await expect(page.getByRole('heading', { level: 1, name: "Murang'a County" })).toBeVisible();
});

test.describe('Kiswahili browser preference', () => {
  test.use({ locale: 'sw-KE' });

  for (const width of [360, 1440]) {
    test(`the first-visit banner leaves the homepage heading clear at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto('/');

      const offer = page.getByRole('complementary').filter({ hasText: 'Ukurasa huu unapatikana kwa Kiswahili.' });
      const header = page.getByRole('banner');
      const heading = page.getByRole('heading', { level: 1 });
      await expect(offer).toBeVisible();
      await expect(heading).toBeVisible();

      const [offerBox, headerBox, headingBox] = await Promise.all([
        offer.boundingBox(), header.boundingBox(), heading.boundingBox(),
      ]);
      if (!offerBox || !headerBox || !headingBox) throw new Error('Expected visible header, language offer, and page heading');
      expect(offerBox.y).toBeGreaterThanOrEqual(headerBox.y + headerBox.height);
      expect(headingBox.y).toBeGreaterThanOrEqual(offerBox.y + offerBox.height);

      await page.evaluate(() => window.scrollTo({ top: 400, behavior: 'instant' }));
      await expect(offer).not.toBeInViewport();
      await expect(header).toBeInViewport();

      await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
      await offer.getByRole('button', { name: 'Endelea kwa Kiingereza' }).click();
      await expect(offer).toHaveCount(0);
      await page.reload();
      await expect(page.locator('html')).toHaveAttribute('lang', 'en');
      await expect(offer).toHaveCount(0);
    });
  }

  test('offers Kiswahili on a first visit and remembers the choice', async ({ page }) => {
    await page.goto('/missing-foundation-test-page');
    await expect(page.getByText('Ukurasa huu unapatikana kwa Kiswahili.')).toBeVisible();
    await page.getByRole('button', { name: 'Tumia Kiswahili' }).click();
    await expect(page.locator('html')).toHaveAttribute('lang', 'sw');
    await page.reload();
    await expect(page.locator('html')).toHaveAttribute('lang', 'sw');
    await expect(page.getByText('Ukurasa huu unapatikana kwa Kiswahili.')).not.toBeVisible();
  });
});
