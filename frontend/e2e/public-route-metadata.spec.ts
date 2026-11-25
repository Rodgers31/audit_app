import { expect, test } from '@playwright/test';
import type { Page } from '@playwright/test';

const routes = [
  { path: '/sources', title: 'Where the data comes from', description: /who publishes the records/i },
  { path: '/learn/government', title: 'How Kenya is governed', description: /national and county governments/i },
  { path: '/learn/why-it-matters', title: 'Why public spending figures matter', description: /health, education and roads/i },
  { path: '/accountability/unaccounted-funds', title: 'Unaccounted funds', description: /Office of the Auditor-General/ },
] as const;

function readHead(page: Page, rawHtml: string) {
  return page.evaluate(html => {
    const { head } = new DOMParser().parseFromString(html, 'text/html');
    const content = (name: string) => head.querySelector(`meta[name="${name}"]`)?.getAttribute('content') ?? null;

    return {
      titles: Array.from(head.querySelectorAll('title'), title => title.textContent),
      description: content('description'),
      robots: content('robots'),
      referrer: content('referrer'),
    };
  }, rawHtml);
}

test('public route titles and descriptions are in the server HTML', async ({ request, page }) => {
  const heads = await Promise.all(routes.map(async ({ path }) => {
    const response = await request.get(path);
    expect(response.ok(), path).toBe(true);
    return readHead(page, await response.text());
  }));

  routes.forEach(({ title, description }, index) => {
    expect(heads[index].titles).toEqual([`${title} | AuditGava`]);
    expect(heads[index].description).toMatch(description);
  });
  expect(new Set(heads.map(head => head.description)).size).toBe(routes.length);
});

test('Sources metadata stays separate from the figure receipt', async ({ request, page }) => {
  // Use the crawler response, which places dynamic metadata in the raw head.
  const options = { headers: { 'User-Agent': 'Twitterbot/1.0' } };
  const rootInheriting = await request.get('/reset-password', options);
  const figure = await request.get('/sources/figures/loans/381', options);
  expect(figure.ok()).toBe(true);
  const baselineHead = await readHead(page, await rootInheriting.text());
  const figureHead = await readHead(page, await figure.text());
  expect(figureHead.titles).toEqual(['Figure evidence | AuditGava']);
  expect(figureHead.description).toBeTruthy();
  expect(figureHead.description).toBe(baselineHead.description);
  expect(figureHead.robots).toBe(baselineHead.robots);
  expect(figureHead.referrer).toBe(baselineHead.referrer);
});

test('Sources keeps its title when the client loads the publisher list', async ({ page }) => {
  await page.route('**/api/v1/sources/summary', route => route.fulfill({
    headers: { 'Access-Control-Allow-Origin': '*' },
    json: {
      total_documents: 1,
      sources: [{
        publisher: 'National Treasury',
        website: 'https://www.treasury.go.ke/',
        document_count: 1,
        last_fetched: null,
        doc_types: {},
      }],
    },
  }));

  await page.goto('/sources');
  await expect(page.getByRole('heading', { name: 'Where the data comes from', level: 1 })).toBeVisible();
  await expect(page.getByText('National Treasury', { exact: true })).toBeVisible();
  await expect(page).toHaveTitle('Where the data comes from | AuditGava');
});
