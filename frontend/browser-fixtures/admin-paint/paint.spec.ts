import { expect, test } from '@playwright/test';

for (const path of ['/admin', '/admin/etl', '/admin/social/new', '/admin/social/example']) {
  test(`critical content is fully visible at its first animation frame on ${path}`, async ({ page }) => {
    await page.goto(path);
    for (const locator of [page.getByRole('heading', { name: 'Critical admin heading' }), page.getByText('Critical working content', { exact: true })]) {
      const opacity = await locator.evaluate(element => {
        let total = 1;
        for (let current: Element | null = element; current; current = current.parentElement) total *= Number(getComputedStyle(current).opacity);
        return total;
      });
      expect(opacity).toBe(1);
    }
  });
}
for (const path of ['/counties', '/administrator']) {
  test(`the public entrance animation is retained on ${path}`, async ({ page }) => {
    await page.goto(path);
    const opacity = await page.getByRole('heading', { name: 'Critical admin heading' }).evaluate(element => {
      let total = 1;
      for (let current: Element | null = element; current; current = current.parentElement) total *= Number(getComputedStyle(current).opacity);
      return total;
    });
    expect(opacity).toBeGreaterThan(0);
    expect(opacity).toBeLessThan(0.1);
  });
}
