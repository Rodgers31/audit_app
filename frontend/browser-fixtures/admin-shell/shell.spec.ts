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

const VIEWPORTS = [{ width: 1728, height: 1000 }, { width: 768, height: 900 }, { width: 375, height: 812 }, { width: 320, height: 568 }];
for (const viewport of VIEWPORTS) {
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

for (const viewport of VIEWPORTS) {
  test(`private utilities remain reachable and functional at ${viewport.width}px`, async ({ page, context }, testInfo) => {
    await page.setViewportSize(viewport);
    await authenticate(context);
    await page.goto('/admin');
    await expect(page.getByRole('heading', { name: 'What needs doing?' })).toBeVisible();
    const account = '#admin-task-navigation + div > a[href="/account"]';
    const theme = '#admin-task-navigation + div button[aria-label^="Switch to"]';
    const publicSite = 'a[aria-label="AuditGava / Admin — public site"]';
    for (const expanded of viewport.width <= 600 ? [false, true] : [false]) {
      if (expanded) await page.getByRole('button', { name: 'Menu', exact: true }).click();
      await reachable(page, account);
      await reachable(page, theme);
      await reachable(page, publicSite);
    }
    await page.screenshot({ path: testInfo.outputPath('private-utilities.png') });
    const wasDark = await page.locator('html').evaluate(el => el.classList.contains('dark'));
    await page.locator(theme).click();
    const nextTheme = wasDark ? 'light' : 'dark';
    await expect.poll(() => page.locator('html').evaluate(el => el.classList.contains('dark'))).toBe(!wasDark);
    expect(await page.evaluate(() => localStorage.getItem('theme'))).toBe(nextTheme);
    await page.reload();
    await expect(page.locator(theme)).toHaveAttribute('aria-label', wasDark ? 'Switch to dark theme' : 'Switch to light theme');
    expect(await page.locator('html').evaluate(el => el.classList.contains('dark'))).toBe(!wasDark);
    expect(await page.evaluate(() => localStorage.getItem('theme'))).toBe(nextTheme);
    await reachable(page, publicSite);
    await page.locator(publicSite).click();
    await expect(page).toHaveURL(/\/$/);
    await expect(page.locator('nav[aria-label="Primary navigation"]')).toHaveCount(1);
    await reachable(page, 'a[aria-label="AuditGava dashboard"]');
    await expect(page.getByRole('navigation', { name: 'Admin navigation' })).toHaveCount(0);
    await page.goBack();
    await expect(page).toHaveURL(/\/admin$/);
    await reachable(page, account);
    await page.locator(account).click();
    await expect(page).toHaveURL(/\/account$/);
    await expect(page.getByRole('heading', { name: 'My Account', exact: true })).toBeVisible();
    expect(await page.locator('html').evaluate(el => el.classList.contains('dark'))).toBe(!wasDark);
    if (viewport.width < 1024) await page.getByRole('button', { name: 'Open navigation menu', exact: true }).click();
    else await page.getByRole('button', { name: 'User menu', exact: true }).click();
    const logout = page.waitForResponse(response => response.url().startsWith('http://127.0.0.1:8137/auth/v1/logout') && response.request().method() === 'POST');
    await page.getByRole(viewport.width < 1024 ? 'button' : 'menuitem', { name: 'Sign out', exact: true }).click();
    expect((await logout).status()).toBe(204);
    await expect(page).toHaveURL(/\/$/);
    await page.goto('/admin');
    await expect(page).toHaveURL(/\/(?:\?.*)?$/);
    await expect(page.getByRole('navigation', { name: 'Admin navigation' })).toHaveCount(0);
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
