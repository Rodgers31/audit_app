import { expect, test as base, type Page } from '@playwright/test';

// Crawler requests receive completed server metadata in the original HTML head.
const test = base.extend<{ crawlerPage: Page }>({
  crawlerPage: async ({ browser, baseURL }, use) => {
    const context = await browser.newContext({
      baseURL,
      javaScriptEnabled: false,
      userAgent: 'Twitterbot/1.0',
    });
    try {
      await use(await context.newPage());
    } finally {
      await context.close();
    }
  },
});

const canonicalBase = 'https://www.auditgava.com';

for (const { alias, name, slug } of [
  { alias: 'Murang%27a', name: "Murang'a", slug: 'Murang%27a' },
  { alias: 'Murang%E2%80%99a', name: "Murang'a", slug: 'Murang%27a' },
  { alias: '021', name: "Murang'a", slug: 'Murang%27a' },
  { alias: 'Taita%20Taveta', name: 'Taita Taveta', slug: 'taita-taveta' },
  { alias: 'taita-taveta', name: 'Taita Taveta', slug: 'taita-taveta' },
  { alias: '001', name: 'Nairobi', slug: 'nairobi' },
  { alias: '047', name: 'Mombasa', slug: 'mombasa' },
  { alias: 'code%3A001', name: 'Mombasa', slug: 'mombasa' },
  { alias: 'code%3A047', name: 'Nairobi', slug: 'nairobi' },
]) {
  test(`serves ${name} metadata for /counties/${alias}`, async ({ crawlerPage: page }) => {
    const response = await page.goto(`/counties/${alias}`);
    expect(response?.ok()).toBe(true);
    const title = `${name} County: budget, debt and audits — AuditGava`;
    const description = `Explore ${name} County’s budget execution, debt, audit findings and accountability.`;
    const canonical = new URL(`/counties/${slug}`, canonicalBase).href;
    const head = page.locator('head');
    const html = await response!.text();
    expect(html.slice(0, html.indexOf('</head>'))).toContain('<title>');

    await expect(page).toHaveTitle(title);
    await expect(head.locator('meta[name="description"]')).toHaveAttribute('content', description);
    await expect(head.locator('link[rel="canonical"]')).toHaveAttribute('href', canonical);
    await expect(head.locator('meta[property="og:title"]')).toHaveAttribute('content', title);
    await expect(head.locator('meta[property="og:description"]')).toHaveAttribute('content', description);
    await expect(head.locator('meta[property="og:url"]')).toHaveAttribute('content', canonical);
    await expect(head.locator('meta[property="og:image"]')).toHaveAttribute('content', /\/og-image\.png$/);
    await expect(head.locator('meta[name="twitter:title"]')).toHaveAttribute('content', title);
    await expect(head.locator('meta[name="twitter:description"]')).toHaveAttribute('content', description);
    await expect(head.locator('meta[name="twitter:image"]')).toHaveAttribute('content', /\/og-image\.png$/);
  });
}

for (const id of ['unknown-county', '4', 'muranga', 'Murang%2527a']) {
  test(`uses generic metadata for unidentified county route /counties/${id}`, async ({ crawlerPage: page }) => {
    await page.goto(`/counties/${id}`);
    const head = page.locator('head');
    await expect(page).toHaveTitle('County detail — AuditGava');
    await expect(head.locator('meta[name="description"]')).toHaveAttribute('content', /Kenya’s counties/);
    await expect(head.locator('meta[property="og:title"]')).toHaveAttribute('content', 'County detail — AuditGava');
    await expect(head.locator('link[rel="canonical"]')).toHaveCount(0);
    await expect(head.locator('meta[property="og:url"]')).toHaveCount(0);
  });
}
