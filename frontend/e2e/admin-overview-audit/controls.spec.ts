import { test, expect, BrowserContext, Page } from '@playwright/test';
import { createHmac } from 'crypto';
const id = '00000000-0000-4000-8000-000000000001';
function token(uid = id) {
  const b64 = (v: unknown) => Buffer.from(JSON.stringify(v)).toString('base64url');
  const body = `${b64({ alg: 'HS256', typ: 'JWT' })}.${b64({ sub: uid, aud: 'authenticated', role: 'authenticated', email: 'admin@example.invalid', exp: Math.floor(Date.now() / 1000) + 3600 })}`;
  return `${body}.${createHmac('sha256', 'admin-overview-audit-inert-key').update(body).digest('base64url')}`;
}
async function signIn(context: BrowserContext, uid = id) {
  const user = { id: uid, aud: 'authenticated', role: 'authenticated', email: 'admin@example.invalid', app_metadata: {}, user_metadata: {} };
  const session = { access_token: token(uid), refresh_token: 'inert-refresh', expires_at: Math.floor(Date.now() / 1000) + 3600, expires_in: 3600, token_type: 'bearer', user };
  await context.addCookies([{ name: 'sb-127-auth-token', value: 'base64-' + Buffer.from(JSON.stringify(session)).toString('base64url'), domain: '127.0.0.1', path: '/', httpOnly: false, secure: false, sameSite: 'Lax' }]);
}
async function localOnly(page: Page) {
  await page.route('**/*', route => {
    const url = new URL(route.request().url());
    return ['127.0.0.1', 'localhost'].includes(url.hostname) ? route.continue() : route.abort();
  });
}
test.beforeEach(async ({ context, page, request }) => {
  await request.post('http://127.0.0.1:8153/__fixture/mode/normal');
  await signIn(context); await localOnly(page);
});

test('actual audit API, filters, snapshot pagination, back history, payload and refresh failures', async ({ page, request }) => {
  const response = await request.get('http://127.0.0.1:8153/api/v1/admin/audit-log?days=0', { headers: { Authorization: 'Bearer ' + token() } });
  expect(response.headers()['cache-control']).toBe('private, no-store');
  expect(await response.text()).not.toContain('INERT_SECRET');
  await page.goto('/admin/audit-log?days=0');
  await expect(page.getByRole('heading', { name: 'Audit Log', exact: true })).toBeVisible();
  await expect(page.getByText('28 actions recorded.')).toBeVisible();
  await expect(page.locator('main li').last()).toHaveCSS('opacity', '1');
  await page.screenshot({ path: '/tmp/admin-overview-audit-desktop.png', fullPage: true });
  await page.getByLabel('Action', { exact: true }).fill('etl.trigger');
  await page.getByLabel('Target id', { exact: true }).fill('cob');
  await page.getByRole('button', { name: 'Apply filters' }).click();
  await expect(page).toHaveURL(/target_id=cob/);
  await expect(page.getByRole('button', { name: 'Next', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: 'Next', exact: true }).click();
  await expect(page).toHaveURL(/snapshot_id=28/);
  await expect(page.getByText('Page 2', { exact: true })).toBeVisible();
  await page.goBack();
  await expect(page.getByLabel('Action', { exact: true })).toHaveValue('etl.trigger');
  await page.getByRole('button', { name: /etl.trigger on etl_source/ }).first().click();
  await expect(page.getByText('Payload', { exact: true }).first()).toBeVisible();
  expect(await page.locator('main').innerText()).not.toContain('INERT_SECRET');
  await request.post('http://127.0.0.1:8153/__fixture/mode/audit-error');
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(page.getByText(/Could not load audit log/)).toBeVisible();
  await request.post('http://127.0.0.1:8153/__fixture/mode/audit-malformed');
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(page.getByText(/Could not load audit log/)).toBeVisible();
});

test('overview cards and mobile keyboard navigation preserve shell and truthful scope', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/admin');
  await expect(page.getByText('Worker execution unverified', { exact: true })).toBeVisible();
  await expect(page.getByText('Profile records', { exact: true })).toBeVisible();
  await expect(page.getByText('Publishing disabled', { exact: true })).toBeVisible();
  await expect(page.locator('main section').last()).toHaveCSS('opacity', '1');
  await page.screenshot({ path: '/tmp/admin-overview-audit-mobile.png', fullPage: true });
  const nav = page.getByRole('navigation', { name: 'Admin navigation' });
  await expect(nav.getByRole('link', { name: 'Overview', exact: true })).toHaveAttribute('aria-current', 'page');
  const audit = nav.getByRole('link', { name: 'Audit Log', exact: true });
  await audit.focus(); await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/\/admin\/audit-log/);
  await expect(audit).toHaveAttribute('aria-current', 'page');
  await expect(page.getByText('28 actions recorded.')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test('deep empty page recovers and invalid URL numbers stay bounded', async ({ page }) => {
  await page.goto('/admin/audit-log?page=999&days=0');
  await expect(page.getByText(/No entries on this page/)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Prev', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(page.getByText('Page 1', { exact: true })).toBeVisible();
  await page.goto('/admin/audit-log?page=NaN&days=-1');
  await expect(page.getByLabel('Time window')).toHaveValue('30');
  await expect(page.getByText('Page 1', { exact: true })).toBeVisible();
  await page.goto('/admin/audit-log?snapshot_id=NaN&as_of=2026-10-08T00%3A00%3A00Z&visibility_snapshot=3%3A9%3A');
  await expect(page.getByText('28 actions recorded.')).toBeVisible();
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(page).toHaveURL('/admin/audit-log?days=30&page=1');
  await expect(page.getByText('28 actions recorded.')).toBeVisible();
});

test('documented Operations health contract keeps available plan distinct from unverified worker', async ({ page }) => {
  await page.route('**/api/v1/admin/etl/health', route => route.fulfill({ json: {
    timestamp: new Date().toISOString(), scheduler_status: 'unverified', plan_status: 'available', worker_status: 'unverified', data_freshness: 'unverified',
  } }));
  await page.goto('/admin');
  await expect(page.getByText('Schedule calculated', { exact: true })).toBeVisible();
  await expect(page.getByText('Worker execution unverified', { exact: true })).toBeVisible();
  await expect(page.locator('main').getByRole('alert')).toHaveCount(0);
});

test('anonymous and citizen sessions cannot render or read audit evidence', async ({ page, context, request }) => {
  await context.clearCookies();
  await page.goto('/admin/audit-log');
  await expect(page).toHaveURL(/authRequired=1/);
  await signIn(context, '00000000-0000-4000-8000-000000000002');
  await page.goto('/admin/audit-log');
  await expect(page).toHaveURL(/unauthorized=1/);
  expect((await request.get('http://127.0.0.1:8153/api/v1/admin/audit-log')).status()).toBe(401);
  expect((await request.get('http://127.0.0.1:8153/api/v1/admin/audit-log', { headers: { Authorization: 'Bearer ' + token('00000000-0000-4000-8000-000000000002') } })).status()).toBe(403);
});
