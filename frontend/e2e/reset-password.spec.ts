import { expect, test } from '@playwright/test';

const selector = 'a'.repeat(32);
const matching = 'InertPass123!';
const reset = '/reset-password#recovery-flow=' + selector;

test.use({ hasTouch: true, viewport: { width: 360, height: 760 }, reducedMotion: 'reduce' });

test('reset form has its own title, readable guidance and keyboard/touch affordances', async ({ page, browserName }) => {
  await page.goto(reset);
  await expect(page).toHaveTitle('Reset password | AuditGava');
  const region = page.getByRole('region', { name: 'Choose a new password' });
  await expect(region.getByText(/up to five minutes/)).toBeVisible();
  const input = region.getByLabel('New password', { exact: true });
  const confirm = region.getByLabel('Type it again', { exact: true });
  const save = region.getByRole('button', { name: 'Save password' });
  await expect(input).toHaveAccessibleDescription(/at least 8 characters.*uppercase.*lowercase.*number/);
  await expect(save).toBeDisabled();

  await input.focus();
  // WebKit on macOS uses Option-Tab to include buttons in sequential focus.
  const tabKey = browserName === 'webkit' && process.platform === 'darwin' ? 'Alt+Tab' : 'Tab';
  await page.keyboard.press(tabKey);
  const show = region.getByRole('button', { name: 'Show new password' });
  await expect(show).toBeFocused();
  await page.keyboard.press('Space');
  await expect(input).toHaveAttribute('type', 'text');
  await region.getByRole('button', { name: 'Hide new password' }).tap();
  await expect(input).toHaveAttribute('type', 'password');

  await input.fill(matching);
  await confirm.fill('InertMismatch123!');
  await expect(confirm).toHaveAccessibleDescription('Passwords do not match.');
  await expect(save).toBeDisabled();
  await confirm.fill(matching);
  await expect(save).toBeEnabled();
});

test('pending submission is disabled, failed response is announced and success redirects', async ({ page }) => {
  const requests: unknown[] = [];
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/auth/reset-password', async route => {
    requests.push(route.request().postDataJSON());
    if (requests.length === 1) {
      await pending;
      await route.fulfill({ status: 400, json: { error: 'Synthetic reset refusal.' } });
      return;
    }
    await route.fulfill({ json: { ok: true } });
  });
  await page.goto(reset);
  const region = page.getByRole('region', { name: 'Choose a new password' });
  await region.getByLabel('New password', { exact: true }).fill(matching);
  await region.getByLabel('Type it again').fill(matching);
  await region.getByRole('button', { name: 'Save password' }).tap();
  await expect(region.getByRole('button', { name: 'Saving password…' })).toBeDisabled();
  await expect.poll(() => requests.length).toBe(1);
  await region.locator('form').evaluate(form => form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  release();
  await expect(region.getByRole('alert')).toHaveText('Synthetic reset refusal.');
  expect(requests).toEqual([{ password: matching, flow: selector }]);

  await region.getByRole('button', { name: 'Save password' }).tap();
  const updated = page.getByRole('heading', { name: 'Password updated' });
  await expect(updated).toBeFocused();
  await expect(page.getByText('Taking you to the homepage…')).toBeVisible();
  await expect(page).toHaveURL('/');
  expect(requests).toHaveLength(2);
});

test('an invalid link has a path home and no password form', async ({ page }) => {
  await page.goto('/reset-password?error=Invalid+reset+link.');
  const region = page.getByRole('region', { name: 'Reset password' });
  await expect(region.getByRole('alert')).toHaveText('Invalid reset link.');
  await expect(region.getByRole('link', { name: 'Back to homepage' })).toHaveAttribute('href', '/');
  await expect(region.getByLabel('New password', { exact: true })).toHaveCount(0);
});
