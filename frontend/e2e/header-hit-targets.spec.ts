import { expect, test, type Locator, type Page } from '@playwright/test';

async function useFallbackTextSpacing(page: Page) {
  await page.addStyleTag({ content: `
    header nav a {
      font-family: Arial, sans-serif !important;
      font-size: 14px !important;
      letter-spacing: 0.12em !important;
      word-spacing: 0.16em !important;
    }
    [role="dialog"] nav a {
      font-family: Arial, sans-serif !important;
      letter-spacing: 0.12em !important;
      word-spacing: 0.16em !important;
    }
  ` });
}

async function expectOwnedHitTarget(target: Locator) {
  await expect(target).toBeVisible();
  const points = await target.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    return [[0.5, 0.5], [0.15, 0.5], [0.85, 0.5]].map(([dx, dy]) => {
      const hit = document.elementFromPoint(rect.x + rect.width * dx, rect.y + rect.height * dy);
      return {
        owned: hit === element || !!hit && element.contains(hit),
        x: rect.x + rect.width * dx,
        y: rect.y + rect.height * dy,
        viewport: [window.innerWidth, window.innerHeight],
        interceptor: hit?.closest('a,button')?.outerHTML.slice(0, 180) ?? hit?.tagName,
      };
    });
  });
  expect(points, `Hit target ${await target.textContent()} must own its visible points`).toEqual(
    points.map((point) => ({ ...point, owned: true })),
  );
}

const choices = { en: 'English', sw: 'Kiswahili', plain: 'Plain English' };

for (const [lang, choice] of Object.entries(choices)) {
  test(`header hit targets and routes stay reachable with fallback fonts: ${lang}`, async ({ page }, testInfo) => {
    await page.addInitScript((value) => localStorage.setItem('auditgava-lang', value), lang);
    await page.route(/fonts\.(?:googleapis|gstatic)\.com/, (route) => route.abort());
    await page.goto('/learn');
    const header = page.locator('header').first();
    await expect(header.getByRole('button', { name: /Switch to .* theme/ })).toBeVisible();
    // A wider fallback and WCAG text-spacing stress must not make sibling
    // navigation links paint over language, theme or authentication controls.
    await useFallbackTextSpacing(page);

    for (const width of [1024, 1280, 1281, 1366, 1439, 1440, 1536, 1920, 2560]) {
      await page.setViewportSize({ width, height: 900 });
      const navigation = header.getByRole('navigation');
      const language = header.locator('summary').first();
      await expectOwnedHitTarget(language);
      const theme = header.getByRole('button', { name: /Switch to .* theme/ });
      await expectOwnedHitTarget(theme);
      await expectOwnedHitTarget(header.getByRole('button', { name: /^(Sign in|Ingia)$/ }));
      await expectOwnedHitTarget(header.getByRole('button', { name: /^(Search AuditGava|Tafuta kwenye AuditGava)$/ }));
      const links = navigation.getByRole('link');
      await expect(links).toHaveCount(6);
      const navBox = (await navigation.boundingBox())!;
      for (const link of await links.all()) {
        await expectOwnedHitTarget(link);
        const box = (await link.boundingBox())!;
        expect(box.x).toBeGreaterThanOrEqual(navBox.x - 1);
        expect(box.x + box.width).toBeLessThanOrEqual(navBox.x + navBox.width + 1);
        expect(box.y).toBeGreaterThanOrEqual(navBox.y - 1);
        expect(box.y + box.height).toBeLessThanOrEqual(navBox.y + navBox.height + 1);
      }
      // Actual clicks, without force or timeout exceptions, exercise the
      // language controls that the original hosted cases could not reach.
      await language.click();
      for (const name of Object.values(choices)) {
        await expectOwnedHitTarget(header.getByRole('radio', { name, exact: true }));
      }
      await expect(header.getByRole('radio', { name: choice, exact: true })).toBeChecked();
      await language.click();
      if (width === 1280) {
        await header.screenshot({ path: testInfo.outputPath(`header-${lang}-1280.png`) });
      }
    }
  });

  test(`mobile header and menu keep their controls reachable: ${lang}`, async ({ page }, testInfo) => {
    await page.addInitScript((value) => localStorage.setItem('auditgava-lang', value), lang);
    await page.route(/fonts\.(?:googleapis|gstatic)\.com/, (route) => route.abort());
    await page.goto('/learn');
    const header = page.locator('header').first();
    await useFallbackTextSpacing(page);
    for (const viewport of [{ width: 320, height: 568 }, { width: 390, height: 844 },
      { width: 768, height: 1024 }, { width: 1023, height: 900 }]) {
      await page.setViewportSize(viewport);
      await expect(header.getByRole('button', { name: /Switch to .* theme/ })).not.toBeVisible();
      await expect(header.getByRole('button', { name: /^(Sign in|Ingia)$/ })).not.toBeVisible();
      const toggle = header.getByRole('button', { name: /Open navigation menu|Fungua menyu/ });
      await expectOwnedHitTarget(toggle);
      await toggle.click();
      const menu = page.getByRole('dialog', { name: /Mobile navigation|Urambazaji wa simu/ });
      await expect(menu).toBeVisible();
      const links = menu.getByRole('navigation').getByRole('link');
      await expect(links).toHaveCount(9);
      for (const link of await links.all()) {
        await link.scrollIntoViewIfNeeded();
        await expectOwnedHitTarget(link);
      }
      if (viewport.width === 320) {
        // A mouse user must be able to scroll the drawer itself, with the
        // underlying page still locked, to reach its language/auth controls.
        const bounds = (await menu.boundingBox())!;
        await page.mouse.move(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2);
        await page.mouse.wheel(0, viewport.height);
        await expect(menu.getByRole('button', { name: /^(Sign in|Ingia)$/ })).toBeInViewport();
      }
      const active = menu.getByRole('radio', { name: choice, exact: true });
      await active.scrollIntoViewIfNeeded();
      await expectOwnedHitTarget(active);
      await active.check();
      await expect(active).toBeChecked();
      const signIn = menu.getByRole('button', { name: /^(Sign in|Ingia)$/ });
      await signIn.scrollIntoViewIfNeeded();
      await expectOwnedHitTarget(signIn);
      if (viewport.width === 320) {
        await page.screenshot({ path: testInfo.outputPath(`menu-${lang}-320.png`) });
      }
      await page.keyboard.press('Escape');
      await expect(menu).not.toBeVisible();
      await expect(toggle).toBeFocused();
      expect(await page.evaluate(() => document.body.style.overflow)).not.toBe('hidden');
    }
  });
}

test('wrapped desktop navigation retains keyboard order and control actions', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('auditgava-lang', 'en'));
  await page.route(/fonts\.(?:googleapis|gstatic)\.com/, (route) => route.abort());
  await page.goto('/learn');
  await useFallbackTextSpacing(page);
  const header = page.locator('header').first();
  await expect(header.getByRole('button', { name: /Switch to .* theme/ })).toBeVisible();
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Skip to main content' })).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(header.getByRole('link', { name: 'AuditGava', exact: true })).toBeFocused();
  for (const link of await header.getByRole('navigation', { name: 'Primary navigation', exact: true }).getByRole('link').all()) {
    await page.keyboard.press('Tab');
    await expect(link).toBeFocused();
    await expectOwnedHitTarget(link);
  }
  await page.keyboard.press('Tab');
  const chooser = header.locator('summary').first();
  await expect(chooser).toBeFocused();
  await page.keyboard.press('Enter');
  await page.keyboard.press('Tab');
  await expect(header.getByRole('radio', { name: 'English', exact: true })).toBeFocused();
  await page.keyboard.press('ArrowRight');
  await expect(header.getByRole('radio', { name: 'Kiswahili', exact: true })).toBeChecked();
  await page.keyboard.press('ArrowLeft');
  await expect(header.getByRole('radio', { name: 'English', exact: true })).toBeChecked();
  await page.keyboard.press('Escape');
  await expect(chooser).toBeFocused();
  await page.keyboard.press('Tab');
  const theme = header.getByRole('button', { name: /Switch to .* theme/ });
  await expect(theme).toBeFocused();
  const before = await theme.getAttribute('aria-label');
  await page.keyboard.press('Enter');
  await expect(theme).not.toHaveAttribute('aria-label', before!);
  await page.keyboard.press('Tab');
  await expect(header.getByRole('button', { name: 'Sign in', exact: true })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('heading', { name: 'Welcome back', exact: true })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('heading', { name: 'Welcome back', exact: true })).not.toBeVisible();
});

test('public search works from the desktop header and inside the mobile drawer', async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 800 });
  await page.goto('/learn');
  const header = page.locator('header').first();
  const searchButton = header.getByRole('button', { name: 'Search AuditGava', exact: true });
  await expect(searchButton).toBeEnabled();
  await searchButton.focus();
  await page.keyboard.press('Enter');
  const desktop = page.getByRole('dialog', { name: 'Search AuditGava', exact: true });
  const input = desktop.getByRole('searchbox');
  await expect(input).toBeFocused();
  await input.fill('Baringo');
  await expect(desktop.getByRole('link', { name: 'Baringo', exact: true })).toHaveAttribute('href', '/counties/baringo');
  await page.keyboard.press('Escape');
  await expect(desktop).toBeHidden();
  await expect(searchButton).toBeFocused();

  await page.setViewportSize({ width: 360, height: 780 });
  await expect(searchButton).toBeHidden();
  const menuButton = header.getByRole('button', { name: 'Open navigation menu' });
  await menuButton.click();
  const drawer = page.getByRole('dialog', { name: 'Mobile navigation' });
  await page.keyboard.press('Tab');
  const drawerSearch = drawer.getByRole('searchbox');
  await expect(drawerSearch).toBeFocused();
  await drawerSearch.fill('214');
  const result = drawer.getByRole('link', { name: 'Article 214 Public debt' });
  await expect(result).toHaveAttribute('href', '/learn?article=214');
  await result.click();
  await expect(drawer).toBeHidden();
  await expect(page).toHaveURL(/\/learn\?article=214$/);
});
