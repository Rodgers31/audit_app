import { expect, test, type Locator, type Page } from '@playwright/test';

async function useFallbackTextSpacing(page: Page) {
  await page.addStyleTag({ content: `
    header nav[aria-label="Primary navigation"] a {
      font-family: Arial, sans-serif !important;
      font-size: 14px !important;
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
        interceptor: hit?.closest('a,button')?.outerHTML.slice(0, 180) ?? hit?.tagName,
      };
    });
  });
  expect(points, `Hit target ${await target.textContent()} must own its visible points`).toEqual(
    points.map((point) => ({ ...point, owned: true })),
  );
}

for (const lang of ['en', 'sw', 'plain']) {
  test(`header hit targets and routes stay reachable with fallback fonts: ${lang}`, async ({ page }, testInfo) => {
    await page.addInitScript((value) => localStorage.setItem('auditgava-lang', value), lang);
    await page.route(/fonts\.(?:googleapis|gstatic)\.com/, (route) => route.abort());
    await page.goto('/learn');
    const header = page.getByRole('banner');
    await expect(header.getByRole('button', { name: /Switch to .* theme/ })).toBeVisible();
    // A wider fallback and WCAG text-spacing stress must not make sibling
    // navigation links paint over language, theme or authentication controls.
    await useFallbackTextSpacing(page);

    for (const width of [1280, 1281, 1366, 1439, 1440, 1536, 1920, 2560]) {
      await page.setViewportSize({ width, height: 900 });
      const navigation = header.getByRole('navigation', { name: 'Primary navigation', exact: true });
      for (const name of ['EN', 'SW', 'Aa']) {
        await expectOwnedHitTarget(header.getByRole('radio', { name, exact: true }));
      }
      const theme = header.getByRole('button', { name: /Switch to .* theme/ });
      await expectOwnedHitTarget(theme);
      await expectOwnedHitTarget(header.getByRole('button', { name: /^(Sign In|Ingia)$/ }));
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
      const active = header.getByRole('radio', { name: lang === 'en' ? 'EN' : lang === 'sw' ? 'SW' : 'Aa', exact: true });
      await active.click();
      await expect(active).toHaveAttribute('aria-checked', 'true');
      if (width === 1280) {
        await header.screenshot({ path: testInfo.outputPath(`header-${lang}-1280.png`) });
      }
    }
  });

  test(`mobile header and menu keep their controls reachable: ${lang}`, async ({ page }, testInfo) => {
    await page.addInitScript((value) => localStorage.setItem('auditgava-lang', value), lang);
    await page.route(/fonts\.(?:googleapis|gstatic)\.com/, (route) => route.abort());
    await page.goto('/learn');
    const header = page.getByRole('banner');
    for (const viewport of [{ width: 320, height: 568 }, { width: 390, height: 844 },
      { width: 768, height: 1024 }, { width: 1279, height: 900 }]) {
      await page.setViewportSize(viewport);
      await expectOwnedHitTarget(header.getByRole('button', { name: /Switch to .* theme/ }));
      await expectOwnedHitTarget(header.getByRole('button', { name: /^(Sign In|Ingia)$/ }));
      const toggle = header.getByRole('button', { name: 'Open navigation menu' });
      await expectOwnedHitTarget(toggle);
      await toggle.click();
      const menu = page.getByRole('dialog', { name: 'Mobile navigation' });
      await expect(menu).toBeVisible();
      const links = menu.getByRole('navigation').getByRole('link');
      await expect(links).toHaveCount(6);
      for (const link of await links.all()) {
        await link.scrollIntoViewIfNeeded();
        await expectOwnedHitTarget(link);
      }
      const active = menu.getByRole('radio', { name: lang === 'en' ? 'EN' : lang === 'sw' ? 'SW' : 'Aa', exact: true });
      await active.scrollIntoViewIfNeeded();
      await expectOwnedHitTarget(active);
      await active.click();
      await expect(active).toHaveAttribute('aria-checked', 'true');
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
  const header = page.getByRole('banner');
  await expect(header.getByRole('button', { name: /Switch to .* theme/ })).toBeVisible();
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Skip to main content' })).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(header.getByRole('link', { name: 'AuditGava dashboard' })).toBeFocused();
  for (const link of await header.getByRole('navigation', { name: 'Primary navigation', exact: true }).getByRole('link').all()) {
    await page.keyboard.press('Tab');
    await expect(link).toBeFocused();
    await expectOwnedHitTarget(link);
  }
  for (const name of ['EN', 'SW', 'Aa']) {
    await page.keyboard.press('Tab');
    const language = header.getByRole('radio', { name, exact: true });
    await expect(language).toBeFocused();
    await page.keyboard.press('Space');
    await expect(language).toHaveAttribute('aria-checked', 'true');
  }
  await page.keyboard.press('Tab');
  const theme = header.getByRole('button', { name: /Switch to .* theme/ });
  await expect(theme).toBeFocused();
  const before = await theme.getAttribute('aria-label');
  await page.keyboard.press('Enter');
  await expect(theme).not.toHaveAttribute('aria-label', before!);
  await page.keyboard.press('Tab');
  await expect(header.getByRole('button', { name: 'Sign In', exact: true })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('heading', { name: 'Welcome back', exact: true })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('heading', { name: 'Welcome back', exact: true })).not.toBeVisible();
});
