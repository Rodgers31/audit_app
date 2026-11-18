/**
 * Side-by-side county comparison (/counties/compare?ids=...)
 */
import { devices, expect, test } from '@playwright/test';
import { pageShell, waitForAppReady } from './utils/selectors';

test.describe('/counties/compare', () => {
  test('empty state prompts user to pick ≥2 counties', async ({ page }) => {
    await page.goto('/counties/compare');
    await waitForAppReady(page);

    await expect(pageShell.h1(page)).toContainText(/Compare counties|Linganisha Kaunti/i);
    await expect(
      page.getByText(/Pick at least two counties|Chagua angalau kaunti mbili/i)
    ).toBeVisible({ timeout: 15_000 });
  });

  test('deep link with ?ids=… pre-populates the table', async ({ page }) => {
    await page.goto('/counties/compare?ids=047,001,032');
    await waitForAppReady(page);

    // Table column headers should include each county
    await expect(page.getByRole('columnheader', { name: /Mombasa/i }).first()).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole('columnheader', { name: /Nairobi/i }).first()).toBeVisible();
    await expect(page.getByRole('columnheader', { name: /Nakuru/i }).first()).toBeVisible();

    // Section headers
    for (const s of ['Population & budget', 'Execution', 'Financial health']) {
      await expect(page.getByText(s, { exact: false }).first()).toBeVisible();
    }
  });

  test('county names in the table link to detail pages', async ({ page }) => {
    await page.goto('/counties/compare?ids=047,001');
    await waitForAppReady(page);

    const mombasaLink = page.getByRole('link', { name: /^Mombasa$/ }).first();
    await expect(mombasaLink).toBeVisible({ timeout: 15_000 });
    const href = await mombasaLink.getAttribute('href');
    expect(href).toMatch(/\/counties\/[\w-]+/);
  });
});

test.describe('county comparison picker interactions', () => {
  test('searches with the keyboard and prevents the same county appearing twice', async ({ page }) => {
    await page.goto('/counties/compare?ids=047,047');
    const first = page.getByRole('combobox', { name: 'County 1' });
    const second = page.getByRole('combobox', { name: 'County 2' });
    await expect(first).toHaveValue('Mombasa');
    await expect(second).toHaveValue('');
    await expect(page.getByRole('note')).toHaveCount(0);

    await second.focus();
    await second.pressSequentially('Mombasa');
    await expect(page.getByRole('status').filter({ hasText: 'No counties match.' })).toBeVisible();
    await expect(page.getByRole('option', { name: 'Mombasa' })).toHaveCount(0);
    await second.press('Escape');
    await expect(second).toBeFocused();
    await expect(second).toHaveValue('');
    await second.fill('NAÍROBI County');
    await second.press('ArrowDown');
    await expect(page.getByRole('option', { name: 'Nairobi' })).toHaveAttribute('aria-selected', 'true');
    await second.press('Enter');
    await expect(second).toHaveValue('Nairobi');
    await expect(second).toBeFocused();
    await expect(page).toHaveURL(/ids=047,001$/);
    await expect(page.getByRole('note').filter({ hasText: 'Pending bills' })).toBeVisible();
    await expect(page.getByText(/Tap or select a county name/)).toBeVisible();
    await page.reload();
    await expect(second).toHaveValue('Nairobi');
    await expect(page.getByRole('table')).toBeVisible();

    await second.focus();
    await second.press('ArrowUp');
    await expect(page.getByRole('option', { name: 'Clear county' })).toHaveAttribute('aria-selected', 'true');
    await second.press('Enter');
    await expect(second).toHaveValue('');
    await expect(page).toHaveURL(/ids=047$/);
  });

  test('suggested pair buttons select the linked county IDs in order', async ({ page }) => {
    await page.goto('/counties/compare');

    for (const [first, second] of [['Nairobi', 'Kiambu'], ['Turkana', 'Marsabit']]) {
      await page.getByRole('button', { name: `${first} vs ${second}` }).click();
      const table = page.getByRole('table');
      const firstLink = table.getByRole('link', { name: first, exact: true });
      const secondLink = table.getByRole('link', { name: second, exact: true });
      await expect(firstLink).toBeVisible();
      await expect(secondLink).toBeVisible();
      const ids = await Promise.all([firstLink, secondLink].map(async (link) => (await link.getAttribute('href'))?.split('/').at(-1)));
      await expect(page).toHaveURL(new RegExp(`ids=${ids.join(',')}$`));
      await expect(page.getByRole('combobox', { name: 'County 1' })).toHaveValue(first);
      await expect(page.getByRole('combobox', { name: 'County 2' })).toHaveValue(second);
    }
  });

  test('supports phone taps and adding and removing a third county', async ({ browser }, testInfo) => {
    test.skip(testInfo.project.name === 'firefox', 'Firefox does not support Playwright mobile emulation.');
    const phone = await browser.newContext({
      ...devices['iPhone 13'],
      viewport: { width: 360, height: 800 },
      reducedMotion: 'reduce',
      baseURL: testInfo.project.use.baseURL,
    });
    try {
      const page = await phone.newPage();
      await page.goto('/counties/compare?ids=047,001');
      const first = page.getByRole('combobox', { name: 'County 1' });
      const second = page.getByRole('combobox', { name: 'County 2' });
      await expect(first).toHaveValue('Mombasa');
      await expect(second).toHaveValue('Nairobi');
      const firstBox = (await first.boundingBox())!;
      const secondBox = (await second.boundingBox())!;
      expect(firstBox.y).toBe(secondBox.y);
      expect(firstBox.x + firstBox.width).toBeLessThan(secondBox.x);
      expect(firstBox.height).toBeGreaterThanOrEqual(44);
      await expect(first).toHaveCSS('font-size', '16px');

      await page.getByRole('button', { name: 'Add a county' }).tap();
      const third = page.getByRole('combobox', { name: 'County 3' });
      await expect(third).toBeFocused();
      await third.fill('Nakuru');
      await page.getByRole('option', { name: 'Nakuru' }).tap();
      await expect(third).toHaveValue('Nakuru');
      await expect(page).toHaveURL(/ids=047,001,032$/);

      await page.getByRole('button', { name: 'Remove county 3' }).tap();
      await expect(third).toHaveCount(0);
      await expect(second).toBeFocused();
      await expect(page).toHaveURL(/ids=047,001$/);
    } finally {
      await phone.close();
    }
  });
});
