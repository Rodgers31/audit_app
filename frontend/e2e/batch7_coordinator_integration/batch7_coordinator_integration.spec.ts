import { test, expect, type APIRequestContext, type Page } from '@playwright/test';
import { createHash, createHmac } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';

const fixture = 'http://127.0.0.1:8163';
const actor = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const encode = (value: unknown) => Buffer.from(JSON.stringify(value)).toString('base64url');
function tokenFor(uid = actor) {
  const input = encode({ alg: 'HS256', typ: 'JWT' }) + '.' + encode({
    sub: uid, email: 'coordinator@example.invalid', exp: 4102444800, aud: 'authenticated',
    role: 'authenticated', session_id: 'inert-coordinator-session',
  });
  return input + '.' + createHmac('sha256', 'batch7-coordinator-inert-signing-key-for-local-tests').update(input).digest('base64url');
}
const auth = { Authorization: 'Bearer ' + tokenFor() };
const unexpectedByPage = new WeakMap<Page, string[]>();
const generatorSha = createHash('sha256').update(readFileSync(__filename)).digest('hex');

async function state(request: APIRequestContext) {
  return (await request.get(fixture + '/fixture/state')).json();
}
async function config(request: APIRequestContext, data: Record<string, unknown>) {
  expect((await request.post(fixture + '/fixture/config', { data })).status()).toBe(200);
}
async function capability(request: APIRequestContext) {
  const response = await request.get(fixture + '/api/v1/admin/etl/dispatch', { headers: auth });
  expect(response.status()).toBe(200);
  return response.json();
}
async function activate(request: APIRequestContext, mode = 'normal') {
  await config(request, { enabled: true, mode });
  expect((await request.post(fixture + '/fixture/worker/start')).status()).toBe(200);
  await expect.poll(async () => (await capability(request)).available).toBe(true);
  return capability(request);
}
async function accept(request: APIRequestContext, generation: string, dry_run = true, key = crypto.randomUUID()) {
  return request.post(fixture + '/api/v1/admin/etl/trigger/oag', {
    headers: { ...auth, 'Idempotency-Key': key }, data: { dry_run, dispatch_generation: generation },
  });
}
async function terminal(request: APIRequestContext, id: string, expected = 'completed') {
  await expect.poll(async () => {
    const response = await request.get(fixture + '/api/v1/admin/etl/commands/' + id, { headers: auth });
    return (await response.json()).status;
  }).toBe(expected);
}
async function renew(page: Page) {
  await page.evaluate(async token => {
    const client = (globalThis as unknown as {
      __KPM_SUPABASE_BROWSER_CLIENT__: { auth: { setSession: (value: unknown) => Promise<unknown> } };
    }).__KPM_SUPABASE_BROWSER_CLIENT__;
    await client.auth.setSession({ access_token: token, refresh_token: 'inert-coordinator-refresh' });
  }, tokenFor());
}
async function snapshot(page: Page, path: string) {
  await expect.poll(() => page.locator('.page-shell-content').evaluate(element => getComputedStyle(element).opacity)).toBe('1');
  await page.screenshot({ path, fullPage: true, animations: 'disabled' });
}
async function calendarBoundary(page: Page) {
  await expect(page.getByRole('status').filter({ hasText: 'The calendar controls below are not connected to worker dispatch. Use the dedicated worker controls and command receipts above when available.' })).toBeVisible();
  await expect(page.getByText('No job was accepted.')).toHaveCount(0);
  await expect(page.getByText('no dedicated worker dispatch is connected')).toHaveCount(0);
  for (const name of ['Trigger', 'Dry-run']) {
    const controls = page.getByRole('button', { name, exact: true });
    expect(await controls.count()).toBeGreaterThan(0);
    for (const control of await controls.all()) await expect(control).toBeDisabled();
  }
}
async function acceptedDetail(page: Page) {
  await expect(page.getByText('Command accepted. Queued acceptance is not completed work.')).toBeVisible();
  await page.getByRole('link', { name: 'View accepted command' }).click();
  await expect(page.getByRole('heading', { name: 'Command receipt', exact: true })).toBeVisible();
  return page.url().split('/').pop()!;
}

test.beforeEach(async ({ context, page, request }) => {
  expect((await request.post(fixture + '/fixture/reset')).status()).toBe(200);
  const session = { access_token: tokenFor(), refresh_token: 'inert-coordinator-refresh', token_type: 'bearer',
    expires_in: 360000, expires_at: 4102444800,
    user: { id: actor, email: 'coordinator@example.invalid', aud: 'authenticated', role: 'authenticated', app_metadata: {}, user_metadata: {} } };
  await context.addCookies([{ name: 'sb-127-auth-token', value: 'base64-' + encode(session), domain: '127.0.0.1', path: '/' }]);
  const unexpected: string[] = [];
  unexpectedByPage.set(page, unexpected);
  await page.route('**/*', route => {
    const url = new URL(route.request().url());
    if ([fixture, 'http://127.0.0.1:3163'].includes(url.origin)) return route.continue();
    unexpected.push(url.origin + url.pathname);
    return route.abort();
  });
});
test.afterEach(async ({ page, request }, info) => {
  const provenance = {
    generated_by: 'frontend/e2e/batch7_coordinator_integration/batch7_coordinator_integration.spec.ts',
    generator_sha256: generatorSha, generated_at: new Date().toISOString(),
    target_commit: process.env.BATCH7_COORDINATOR_TARGET_SHA ?? null,
  };
  const observed = JSON.stringify({ ...provenance, test: info.title, verdict: info.status, state: await state(request) }, null, 2);
  const observedPath = info.outputPath('actual-postgresql-observations.json');
  writeFileSync(observedPath, observed + '\n');
  expect(JSON.parse(readFileSync(observedPath, 'utf8')).generator_sha256).toBe(generatorSha);
  await info.attach('actual-postgresql-observations', { path: observedPath, contentType: 'application/json' });
  expect((await request.post(fixture + '/fixture/worker/stop')).status()).toBe(200);
  const unexpected = unexpectedByPage.get(page) ?? [];
  const transportPath = info.outputPath('unexpected-browser-transport.json');
  writeFileSync(transportPath, JSON.stringify({ ...provenance, unexpected }) + '\n');
  expect(JSON.parse(readFileSync(transportPath, 'utf8')).generator_sha256).toBe(generatorSha);
  await info.attach('unexpected-browser-transport', { path: transportPath, contentType: 'application/json' });
  expect(unexpected).toEqual([]);
});

test('actual default-off UI and keyed backend reject without jobs or audits', async ({ page, request }, info) => {
  await page.goto('/admin/etl');
  await expect(page.locator('[aria-labelledby="dispatch-heading"]').getByRole('status').first()).toHaveText('Dedicated worker dispatch is unavailable.');
  await expect(page.getByRole('button', { name: 'Run Now · oag' })).toBeDisabled();
  const response = await accept(request, crypto.randomUUID(), false);
  expect(response.status()).toBe(503);
  expect(response.headers()['cache-control']).toBe('private, no-store');
  expect((await state(request)).counts).toEqual({ commands: 0, audits: 0, jobs: 0, effects: 0 });
  await snapshot(page, info.outputPath('actual-default-off.png'));
});

test('actual confirmed real run completes with persisted actor audit and ingestion receipt', async ({ page, request }, info) => {
  const ready = await activate(request);
  const unsupported = await request.post(fixture + '/api/v1/admin/etl/trigger/knbs', {
    headers: { ...auth, 'Idempotency-Key': crypto.randomUUID() },
    data: { dry_run: false, dispatch_generation: ready.generation },
  });
  expect(unsupported.status()).toBe(503);
  expect((await state(request)).counts).toEqual({ commands: 0, audits: 0, jobs: 0, effects: 0 });
  await page.goto('/admin/etl');
  const run = page.getByRole('button', { name: 'Run Now · oag' });
  await expect(run).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Run Now · treasury' })).toBeDisabled();
  await calendarBoundary(page);
  const legacyHealth = await request.get(fixture + '/api/v1/admin/etl/health', { headers: auth });
  expect(legacyHealth.status()).toBe(200);
  expect((await legacyHealth.json()).manual_trigger).toMatchObject({
    available: false,
    reason: 'Calendar endpoints do not dispatch work or verify worker readiness. Use dedicated dispatch capability and command receipts for execution evidence.',
  });
  await snapshot(page, info.outputPath('actual-worker-ready.png'));
  await run.click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  expect((await state(request)).counts.commands).toBe(0);
  await run.click();
  await page.getByRole('button', { name: 'Confirm Run Now' }).click();
  await expect(page.getByText('Command accepted. Queued acceptance is not completed work.')).toBeVisible();
  await calendarBoundary(page);
  const id = await acceptedDetail(page);
  await expect(page.getByText('Completed — recorded ingestion observation.')).toBeVisible({ timeout: 15000 });
  const actual = await state(request);
  expect(actual.counts).toEqual({ commands: 1, audits: 1, jobs: 1, effects: 1 });
  expect(actual.audits[0]).toEqual({ actor_id: actor, action: 'etl.trigger', target_id: id, payload: { dry_run: false } });
  expect(actual.observations[0]).toMatchObject({ status: 'COMPLETED', dry_run: false, command_id: id, items_created: 1 });
  await expect(page.getByRole('link', { name: /View ingestion observation/ })).toHaveAttribute('href', '/admin/ingestion/' + actual.observations[0].id);
  await snapshot(page, info.outputPath('actual-completed.png'));
});

test('actual dry-run enters native runner and rolls back the inert effect', async ({ page, request }) => {
  await activate(request, 'before');
  await page.goto('/admin/etl');
  await page.getByRole('button', { name: 'Dry Run · oag' }).click();
  const id = await acceptedDetail(page);
  await expect.poll(async () => (await state(request)).markers.length).toBe(1);
  await expect(page.getByText('Running — execution in progress.')).toBeVisible({ timeout: 10000 });
  await config(request, { mode: 'normal' });
  await expect(page.getByText('Completed — recorded ingestion observation.')).toBeVisible({ timeout: 15000 });
  const actual = await state(request);
  expect(actual.counts).toEqual({ commands: 1, audits: 1, jobs: 1, effects: 0 });
  expect(actual.observations[0]).toMatchObject({ status: 'COMPLETED', dry_run: true, command_id: id, items_created: 1 });
  expect(actual.audits[0].payload).toEqual({ dry_run: true });
});

test('lost actual acceptance acknowledgment recovers same key after lease expiry without replay', async ({ page, request }) => {
  await activate(request, 'before');
  const keys: string[] = [];
  let lost = true;
  await page.route('**/api/v1/admin/etl/trigger/oag', async route => {
    keys.push(route.request().headers()['idempotency-key']);
    if (lost) {
      lost = false;
      const accepted = await route.fetch();
      expect(accepted.status()).toBe(202);
      await route.abort();
    } else await route.continue();
  });
  await page.goto('/admin/etl');
  await page.getByRole('button', { name: 'Dry Run · oag' }).click();
  await expect(page.getByRole('button', { name: 'Recover same intent' })).toBeVisible();
  await expect.poll(async () => (await state(request)).markers.length).toBe(1);
  await config(request, { expire_worker: true });
  await page.getByRole('button', { name: 'Refresh worker evidence' }).click();
  await expect(page.getByRole('button', { name: 'Run Now · oag' })).toBeDisabled();
  await page.getByRole('button', { name: 'Recover same intent' }).click();
  await expect(page.getByText('Original receipt recovered. No second command was accepted.')).toBeVisible();
  await expect(page.getByLabel('Dedicated worker dispatch', { exact: true }).getByText('Interrupted — execution unverified. Do not automatically repeat.')).toBeVisible();
  expect(keys).toHaveLength(2);
  expect(keys[1]).toBe(keys[0]);
  expect((await state(request)).counts).toEqual({ commands: 1, audits: 1, jobs: 1, effects: 0 });
});

test('actual restarted generation rejects a stale UI intent before acceptance', async ({ page, request }) => {
  const initial = await activate(request);
  await page.goto('/admin/etl');
  await expect(page.getByRole('button', { name: 'Dry Run · oag' })).toBeEnabled();
  expect((await request.post(fixture + '/fixture/worker/stop')).status()).toBe(200);
  expect((await request.post(fixture + '/fixture/worker/start')).status()).toBe(200);
  await expect.poll(async () => (await capability(request)).available).toBe(true);
  expect((await capability(request)).generation).not.toBe(initial.generation);
  const refused = page.waitForResponse(response => response.url().endsWith('/trigger/oag') && response.status() === 409);
  await page.getByRole('button', { name: 'Dry Run · oag' }).click();
  await refused;
  await expect(page.getByText('Command was not acknowledged. Refresh worker evidence before a new intent.')).toBeVisible();
  expect((await state(request)).counts).toEqual({ commands: 0, audits: 0, jobs: 0, effects: 0 });
  await page.getByRole('button', { name: 'Refresh worker evidence' }).click();
  await expect(page.getByRole('button', { name: 'Dry Run · oag' })).toBeEnabled();
  await page.getByRole('button', { name: 'Dry Run · oag' }).click();
  await acceptedDetail(page);
  await expect(page.getByText('Completed — recorded ingestion observation.')).toBeVisible({ timeout: 15000 });
});

test('actual persisted command history filters, pagination, detail and safe back links agree', async ({ page, request }) => {
  const ready = await activate(request);
  for (let n = 0; n < 3; n++) {
    const response = await accept(request, ready.generation);
    expect(response.status()).toBe(202);
    await terminal(request, (await response.json()).command.id);
  }
  await page.goto('/admin/etl?source=oag&status=completed&page_size=1');
  await expect(page.getByText('1 on this page · 3 commands matching')).toBeVisible();
  await page.getByRole('button', { name: 'Next commands' }).click();
  await expect(page).toHaveURL(/page=2/);
  await expect(page.getByText('Page 2', { exact: true })).toBeVisible();
  await page.getByRole('link', { name: /View command / }).first().click();
  await expect(page.getByRole('heading', { name: 'Command receipt', exact: true })).toBeVisible();
  await expect(page.getByText('Completed — recorded ingestion observation.')).toBeVisible();
  await page.getByRole('link', { name: 'Back to command history' }).click();
  await expect(page.getByLabel('Command status', { exact: true })).toHaveValue('completed');
  await expect(page.getByText('Page 2', { exact: true })).toBeVisible();
  await page.goto('/admin/etl?page=99');
  await expect(page.getByText('No commands match this page.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Previous commands' })).toBeEnabled();
});

test('actual failed runner observation is shown without raw diagnostics', async ({ page, request }) => {
  await activate(request, 'failure');
  await page.goto('/admin/etl');
  await page.getByRole('button', { name: 'Dry Run · oag' }).click();
  const id = await acceptedDetail(page);
  await expect(page.getByText('Failed — execution did not complete.')).toBeVisible({ timeout: 15000 });
  const actual = await state(request);
  expect(actual.counts).toEqual({ commands: 1, audits: 1, jobs: 1, effects: 0 });
  expect(actual.observations[0]).toMatchObject({ status: 'FAILED', command_id: id });
  await expect(page.getByText('Inert coordinator domain failure')).toHaveCount(0);
});

test('actual orphaned execution is interrupted while durable domain exclusion stays occupied', async ({ page, request }, info) => {
  await activate(request, 'after');
  await page.goto('/admin/etl');
  await page.getByRole('button', { name: 'Run Now · oag' }).click();
  await page.getByRole('button', { name: 'Confirm Run Now' }).click();
  const id = await acceptedDetail(page);
  await expect.poll(async () => (await state(request)).markers.some((value: {stage: string}) => value.stage === 'committed')).toBe(true);
  await request.post(fixture + '/fixture/worker/pause-supervisor');
  await config(request, { expire_worker: true });
  await expect(page.getByText('Interrupted — execution unverified. Do not automatically repeat.')).toBeVisible({ timeout: 15000 });
  const actual = await state(request);
  expect(actual.counts).toEqual({ commands: 1, audits: 1, jobs: 1, effects: 1 });
  expect(actual.domains[0].command_id).toBe(id);
  await expect(page.getByRole('button', { name: /Run Now|Recover same intent/ })).toHaveCount(0);
  await snapshot(page, info.outputPath('actual-interrupted-after-effect.png'));
});

for (const refusedStatus of [401, 403]) {
  test('actual initial ' + refusedStatus + ' refusal cannot recover the rejected intent after renewal', async ({ page, request }) => {
    await activate(request);
    const keys: string[] = [];
    await page.goto('/admin/etl');
    await expect(page.getByRole('button', { name: 'Dry Run · oag' })).toBeEnabled();
    if (refusedStatus === 403) await config(request, { profile_role: 'citizen' });
    let initial = true;
    await page.route('**/api/v1/admin/etl/trigger/oag', async route => {
      keys.push(route.request().headers()['idempotency-key']);
      if (initial && refusedStatus === 401) {
        initial = false;
        await route.continue({ headers: { ...route.request().headers(), authorization: 'Bearer invalid-local-signature' } });
      } else await route.continue();
    });
    await page.getByRole('button', { name: 'Dry Run · oag' }).click();
    await expect(page.getByText('Administrator access expired. Renew your session to verify access.')).toBeVisible();
    expect((await state(request)).counts.commands).toBe(0);
    await config(request, { profile_role: 'admin' });
    await renew(page);
    await expect(page.getByRole('button', { name: 'Dry Run · oag' })).toBeEnabled();
    await expect(page.getByRole('button', { name: 'Recover same intent' })).toHaveCount(0);
    await page.getByRole('button', { name: 'Dry Run · oag' }).click();
    await acceptedDetail(page);
    await expect(page.getByText('Completed — recorded ingestion observation.')).toBeVisible({ timeout: 15000 });
    expect(keys).toHaveLength(2);
    expect(keys[1]).not.toBe(keys[0]);
  });
}

test('mobile keyboard confirmation and actual completion stay within viewport', async ({ page, request }, info) => {
  await activate(request);
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto('/admin/etl');
  const run = page.getByRole('button', { name: 'Run Now · oag' });
  await expect(run).toBeEnabled();
  await run.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('button', { name: 'Cancel', exact: true })).toBeFocused();
  await page.keyboard.press('Shift+Tab');
  await expect(page.getByRole('button', { name: 'Confirm Run Now' })).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(run).toBeFocused();
  await run.click();
  await page.getByRole('button', { name: 'Confirm Run Now' }).click();
  await acceptedDetail(page);
  await expect(page.getByText('Completed — recorded ingestion observation.')).toBeVisible({ timeout: 15000 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await snapshot(page, info.outputPath('actual-mobile-completed.png'));
});
