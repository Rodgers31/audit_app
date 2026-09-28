import { expect, test } from '@playwright/test';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
const exec = promisify(execFile);

const api = 'http://127.0.0.1:8125';
async function refresh(secret = 'browser-test-only-secret') {
  return (await exec(process.env.BROWSER_TEST_PYTHON || 'python', ['../backend/tests/run_browser_refresh.py'], {
    encoding: 'utf8', env: { ...process.env, API_BASE_URL: api,
      REVALIDATE_URL: 'http://127.0.0.1:3125/api/revalidate', REVALIDATE_SECRET: secret },
  })).stdout;
}

test('accepted fixture change reaches rendered county page through the signed workflow without deployment', async ({ page, request }) => {
  const before = await request.get(`${api}/api/v1/counties`);
  expect(before.status()).toBe(200);
  expect((await before.json()).find((c: any) => c.code === '047').total_budget).toBe(100000000000);
  await page.goto('/counties');
  await expect(page.getByRole('row').filter({ hasText: 'Nairobi' })).toContainText('100.0B');

  expect((await request.post(`${api}/__fixture/budget/125000000000`)).ok()).toBeTruthy();
  // Positive control: the real backend cache still serves the old value.
  const stale = await request.get(`${api}/api/v1/counties`);
  expect((await stale.json()).find((c: any) => c.code === '047').total_budget).toBe(100000000000);
  expect(stale.headers()['cache-control']).toBe('no-store');

  // Missing config and denied invalidation must stop BEFORE frontend revalidation.
  for (const secret of ['', 'wrong-test-key']) {
    await refresh(secret).then(
      () => { throw new Error('refresh unexpectedly succeeded'); },
      (error) => {
        expect(error.code).toBe(1);
        expect(String(error.stdout)).not.toContain('Revalidate the prerendered pages');
      },
    );
  }
  const receipt = await refresh();
  expect(receipt.indexOf("Invalidate the API's response caches")).toBeLessThan(receipt.indexOf('Revalidate the prerendered pages'));
  expect(receipt).toMatch(/Revalidated \d+ page paths/);
  const changed = await request.get(`${api}/api/v1/counties`);
  expect((await changed.json()).find((c: any) => c.code === '047').total_budget).toBe(125000000000);

  // Block client-side county fetching so this is a server-rendered-data
  // assertion, not a client request accidentally hiding broken ISR.
  await page.route('**/api/v1/counties', route => route.abort());
  await page.reload();
  await expect(page.getByRole('row').filter({ hasText: 'Nairobi' })).toContainText('125.0B');
});
