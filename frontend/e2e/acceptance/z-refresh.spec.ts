import { expect, test } from '@playwright/test';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
const exec = promisify(execFile);

const api = 'http://127.0.0.1:8125';
async function refresh(secret = 'browser-test-only-secret') {
  return (await exec(process.env.BROWSER_TEST_PYTHON || 'python', ['../backend/tests/run_browser_refresh.py'], {
    encoding: 'utf8', env: { ...process.env, REVALIDATE_SECRET: secret },
  })).stdout;
}

test('accepted fixture change reaches rendered county page through the signed workflow without deployment', async ({ page, request }) => {
  const before = await request.get(`${api}/api/v1/counties`);
  expect(before.status()).toBe(200);
  expect((await before.json()).find((c: any) => c.code === '047').total_budget).toBe(100000000000);
  await page.goto('/counties');
  await page.getByRole('button', { name: 'Table view', exact: true }).click();
  await expect(page.getByRole('row').filter({ hasText: 'Nairobi' })).toContainText('100.0B');

  expect((await request.post(`${api}/__fixture/budget/125000000000`)).ok()).toBeTruthy();
  // Positive control: the real backend cache still serves the old value.
  const stale = await request.get(`${api}/api/v1/counties`);
  expect((await stale.json()).find((c: any) => c.code === '047').total_budget).toBe(100000000000);
  expect(stale.headers()['cache-control']).toBe('no-store');

  // Both observations must come from the server-rendered page.
  await page.route('**/api/v1/counties', route => route.abort());
  await page.reload();
  await expect(page.getByRole('row').filter({ hasText: 'Nairobi' })).toContainText('100.0B');

  // Missing config and denied invalidation must stop BEFORE frontend revalidation.
  for (const secret of ['', 'wrong-test-key']) {
    await refresh(secret).then(
      () => { throw new Error('refresh unexpectedly succeeded'); },
      (error) => {
        expect(error.code).toBe(1);
        const stdout = String(error.stdout);
        expect(stdout).not.toContain('Revalidate the prerendered pages');
        expect(stdout).toContain(secret ? 'HTTP Error 401' : 'REVALIDATE_SECRET');
      },
    );
  }
  const receipt = await refresh();
  expect(receipt).toMatch(/backend signed acknowledgment verified[\s\S]*pages signed acknowledgment verified/);
  const changed = await request.get(`${api}/api/v1/counties`);
  expect((await changed.json()).find((c: any) => c.code === '047').total_budget).toBe(125000000000);

  await page.reload();
  await expect(page.getByRole('row').filter({ hasText: 'Nairobi' })).toContainText('125.0B');
});
