import { test, expect } from '@playwright/test';
const actor = '22222222-2222-4222-8222-222222222222';
const target = '00000000-0000-0000-0000-000000000001';
test.beforeEach(async ({ context, page, request }) => {
  await request.post('http://127.0.0.1:8151/fixture/reset');
  const session = {
    access_token: 'fixture-token',
    refresh_token: 'fixture-refresh',
    token_type: 'bearer',
    expires_in: 360000,
    expires_at: 4102444800,
    user: {
      id: actor,
      email: 'admin@example.invalid',
      aud: 'authenticated',
      role: 'authenticated',
      app_metadata: {},
      user_metadata: {},
    },
  };
  await context.addCookies([
    {
      name: 'sb-127-auth-token',
      value: 'base64-' + Buffer.from(JSON.stringify(session)).toString('base64url'),
      domain: '127.0.0.1',
      path: '/',
    },
  ]);
  await page.route(/https:\/\//, (r) => r.abort());
});
test('list pagination, global email search, detail and browser history', async ({ page }) => {
  await page.goto('/admin/users');
  await expect(page.getByText('20 on this page · 42 total matching')).toBeVisible();
  await page.getByRole('button', { name: 'Next', exact: true }).click();
  await expect(page).toHaveURL(/page=2/);
  await page.goBack();
  await expect(page).toHaveURL(/\/admin\/users$/);
  await page.getByRole('textbox', { name: 'Search users by email' }).fill('user40');
  await expect(page.getByRole('link').filter({ hasText: 'user40@example.invalid' })).toBeVisible();
  await page.getByRole('link').filter({ hasText: 'user40@example.invalid' }).click();
  await expect(page.getByText('Roles', { exact: true })).toBeVisible();
  await page.goBack();
  await expect(page.getByRole('textbox', { name: 'Search users by email' })).toHaveValue('user40');
});
test('roles, reset accepted acknowledgment and inert delete confirmation', async ({
  page,
  request,
}) => {
  await page.goto(`/admin/users/${target}`);
  await page.getByRole('button', { name: 'admin', exact: true }).click();
  await page.getByRole('button', { name: 'Save changes' }).click();
  await expect(page.getByText('Roles updated.')).toBeVisible();
  await page.getByRole('button', { name: 'Send', exact: true }).click();
  await expect(page.getByText(/Reset request accepted/)).toBeVisible();
  await page.getByRole('button', { name: 'Delete…' }).click();
  const confirm = page.getByRole('textbox', { name: 'Confirm deletion' });
  await expect(confirm).toBeFocused();
  await confirm.fill('wrong');
  await expect(page.getByRole('button', { name: 'Delete permanently' })).toBeDisabled();
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  await page.getByRole('button', { name: 'Delete…' }).click();
  await confirm.fill('user0@example.invalid');
  await page.getByRole('button', { name: 'Delete permanently' }).click();
  await expect(page).toHaveURL(/\/admin\/users$/);
  const audit = await request.get('http://127.0.0.1:8151/fixture/audit');
  expect((await audit.json()).map((row: { action: string }) => row.action)).toEqual([
    'users.update_roles',
    'users.send_reset',
    'users.delete',
  ]);
});
test('self protection, keyboard controls and mobile layout', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto(`/admin/users/${actor}`);
  await expect(page.getByRole('button', { name: 'admin', exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Delete…' })).toHaveCount(0);
  await page.getByRole('button', { name: 'citizen', exact: true }).focus();
  await page.keyboard.press('Space');
  await expect(page.getByRole('button', { name: 'Save changes' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
test('malformed payload is recoverable and empty later page has Prev', async ({ page }) => {
  let bad = true;
  await page.route('**/api/v1/admin/users?**', (r) =>
    r.fulfill({
      json: bad
        ? { users: [], total: 'broken' }
        : { users: [], total: 0, page: 2, page_size: 20, has_more: false },
    })
  );
  await page.goto('/admin/users?page=2');
  await expect(page.getByText('Could not load users.')).toBeVisible();
  bad = false;
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(page.getByText('No users match.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Prev' })).toBeEnabled();
});
