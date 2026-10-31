import { test, expect, type Page, type BrowserContext } from '@playwright/test';
import { session } from './service.cjs';
import { GET as operations } from '../admin-redesign/operations';
import { GET as social } from '../admin-redesign/api';

export async function authenticate(context: BrowserContext, role = 'admin') {
  await context.addCookies([{ name: 'sb-127-auth-token', value: 'base64-' + Buffer.from(JSON.stringify(session(role))).toString('base64url'), domain: '127.0.0.1', path: '/' }]);
}
export async function inertReads(page: Page) {
  await page.route('**/*', async route => {
    const request = route.request(), url = new URL(request.url());
    if (url.hostname !== '127.0.0.1') return route.abort('blockedbyclient');
    if (!url.pathname.startsWith('/api/v1/')) return route.continue();
    if (request.method() !== 'GET') return route.fulfill({ status: 403, json: { detail: 'All writes held' } });
    const response = await (url.pathname.includes('/admin/social/') ? social : operations)(new Request(url));
    await route.fulfill({ status: response.status, contentType: 'application/json', body: await response.text(), headers: { 'Access-Control-Allow-Origin': '*' } });
  });
}
export async function reachable(page: Page, selector: string) {
  const target = page.locator(selector);
  await expect(target).toBeVisible();
  await target.scrollIntoViewIfNeeded();
  expect(await target.evaluate(el => {
    for (let node: Element | null = el; node; node = node.parentElement) {
      if (Number(getComputedStyle(node).opacity) === 0) return false;
    }
    return true;
  }), `${selector} and its ancestors must be painted`).toBe(true);
  expect(await target.evaluate(el => {
    const r = el.getBoundingClientRect(), top = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
    return top === el || el.contains(top);
  }), `${selector} must receive pointer input without another header covering it`).toBe(true);
}

test.beforeEach(async ({ page }) => { await inertReads(page); });

test('reachability refuses transparent controls and covering headers', async ({ page }) => {
  const link = '<a id="target" href="/admin/social" style="display:block;width:180px;height:44px">Social</a>';
  await page.setContent(link);
  await reachable(page, '#target');
  for (const html of [link.replace('display:block', 'opacity:0;display:block'), `<div style="opacity:0">${link}</div>`]) {
    await page.setContent(html);
    await expect(reachable(page, '#target')).rejects.toThrow(/must be painted/);
  }
  await page.setContent(`${link}<div style="position:fixed;inset:0;background:white;z-index:99">Covering header</div>`);
  await expect(reachable(page, '#target')).rejects.toThrow(/must receive pointer input/);
});

for (const viewport of [{ width: 1728, height: 1000 }, { width: 768, height: 900 }, { width: 375, height: 812 }, { width: 320, height: 568 }]) {
  test(`admin navigation stays visible and clickable at ${viewport.width}px`, async ({ page, context }, testInfo) => {
    await page.setViewportSize(viewport);
    await authenticate(context);
    await page.goto('/admin');
    await expect(page.getByRole('heading', { name: 'What needs doing?' })).toBeVisible();
    if (viewport.width <= 600) await page.getByRole('button', { name: 'Menu', exact: true }).click();
    await page.screenshot({ path: testInfo.outputPath('admin-overview.png') });
    await reachable(page, '#admin-task-navigation a[href="/admin/social"]');
    await expect(page.getByRole('navigation', { name: 'Primary navigation' })).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.getByRole('navigation', { name: 'Admin navigation' }).getByRole('link', { name: 'Social', exact: true }).click();
    await expect(page).toHaveURL(/\/admin\/social$/);
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  });
}

test('all private shell entry points have one reachable task navigation', async ({ page, context }) => {
  await authenticate(context);
  for (const path of ['/admin/social/new', '/admin/ingestion', '/admin/etl', '/admin/users', '/admin/audit-log', '/status']) {
    await page.goto(path);
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    await expect(page.getByRole('navigation', { name: 'Admin navigation' })).toHaveCount(1);
    await reachable(page, '#admin-task-navigation a[href="/status"]');
    await expect(page.getByRole('navigation', { name: 'Primary navigation' })).toHaveCount(0);
  }
});

for (const role of ['signed-out', 'editor']) {
  test(`${role} cannot mount private navigation`, async ({ page, context }) => {
    if (role !== 'signed-out') await authenticate(context, role);
    await page.goto('/admin');
    await expect(page).toHaveURL(/\/(?:\?.*)?$/);
    await expect(page.getByRole('navigation', { name: 'Admin navigation' })).toHaveCount(0);
    await expect(page.getByRole('link', { name: 'AuditGava dashboard' })).toBeVisible();
  });
}
