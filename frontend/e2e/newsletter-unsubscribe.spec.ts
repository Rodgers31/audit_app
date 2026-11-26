import { expect, test } from '@playwright/test';

const address = 'reader@example.com';
const route = '/newsletter/unsubscribe';
const signedRoute = `${route}?email=${encodeURIComponent(address)}&token=${'a'.repeat(64)}`;
const action = '**/api/v1/newsletter/';
const genericReceipt = 'If this address is subscribed, check your inbox for an unsubscribe link.';
const requestError = 'We couldn’t request a link right now. Please try again.';

const crossOrigin = {
  'access-control-allow-origin': '*',
  'access-control-allow-methods': 'POST, OPTIONS',
  'access-control-allow-headers': 'content-type',
};

test('requests a link without account credentials and shows one generic receipt', async ({ page }) => {
  const submitted: unknown[] = [];
  await page.route(`${action}unsubscribe-request`, async intercepted => {
    const request = intercepted.request();
    if (request.method() === 'OPTIONS') return intercepted.fulfill({ status: 204, headers: crossOrigin });
    expect(request.headers().authorization).toBeUndefined();
    expect(request.headers().cookie).toBeUndefined();
    expect(request.headers().referer).toBeUndefined();
    submitted.push(request.postDataJSON());
    return intercepted.fulfill({ status: 202, headers: crossOrigin, json: { status: 'requested' } });
  });
  await page.goto(route);
  await expect(page).toHaveTitle(/Unsubscribe from the digest/);
  const section = page.getByRole('region', { name: 'Unsubscribe from the digest' });
  await expect(section.getByRole('link', { name: 'Home' })).toHaveAttribute('href', '/');
  await section.getByRole('textbox', { name: 'Email' }).fill(address);
  await section.getByRole('button', { name: 'Send unsubscribe link' }).press('Enter');
  const status = section.getByRole('status');
  await expect(status).toHaveText(genericReceipt);
  await expect(status).toBeFocused();
  expect(submitted).toEqual([{ email: address }]);
  await expect(section.getByText(address, { exact: true })).toHaveCount(0);
});

test('keeps the signed confirmation and recovers a rejected link to an empty email field', async ({ page }) => {
  let attempts = 0;
  await page.route(`${action}unsubscribe-verify`, async intercepted => {
    if (intercepted.request().method() === 'OPTIONS') return intercepted.fulfill({ status: 204, headers: crossOrigin });
    attempts += 1;
    const request = intercepted.request().postDataJSON();
    expect(request).toEqual({ email: address, token: 'a'.repeat(64) });
    const response = attempts === 1 ? { status: 200, json: { status: 'already_unsubscribed' } }
      : { status: 403, json: { detail: 'Internal response that should never be shown' } };
    return intercepted.fulfill({ ...response, headers: crossOrigin });
  });
  await page.goto(signedRoute);
  const confirm = page.getByRole('button', { name: 'Unsubscribe', exact: true });
  await expect(confirm).toBeVisible();
  expect(attempts).toBe(0);
  await confirm.press('Enter');
  await expect(page.getByRole('heading', { name: 'You’re unsubscribed' })).toBeVisible();
  await page.reload();
  await confirm.press('Enter');
  const form = page.getByRole('region', { name: 'Unsubscribe from the digest' });
  await expect(form.getByRole('alert')).toHaveText('This link is no longer usable. Request a fresh link below.');
  const email = page.getByRole('textbox', { name: 'Email' });
  await expect(email).toHaveValue('');
  await expect(email).toBeFocused();
  await expect(page.getByText(/Internal response/)).toHaveCount(0);
});

test('keeps delivery request failures generic and allows another submission', async ({ page }) => {
  let attempts = 0;
  await page.route(`${action}unsubscribe-request`, async intercepted => {
    if (intercepted.request().method() === 'OPTIONS') return intercepted.fulfill({ status: 204, headers: crossOrigin });
    const response = ++attempts === 1 ? { status: 503, json: { detail: 'Internal diagnostic' } }
      : { status: 202, json: { status: 'requested' } };
    return intercepted.fulfill({ ...response, headers: crossOrigin });
  });
  await page.goto(route);
  const form = page.getByRole('region', { name: 'Unsubscribe from the digest' });
  const email = page.getByRole('textbox', { name: 'Email' });
  const send = page.getByRole('button', { name: 'Send unsubscribe link' });
  await email.fill(address);
  await send.click();
  await expect(form.getByRole('alert')).toHaveText(requestError);
  await expect(email).toHaveValue(address);
  await expect(page.getByText('Internal diagnostic')).toHaveCount(0);
  await send.click();
  await expect(page.getByRole('status')).toHaveText(genericReceipt);
});

test('times out an unanswered request and recovers without reloading', async ({ page }) => {
  let attempts = 0;
  let releaseFirstRequest: () => void = () => {};
  const holdFirstRequest = new Promise<void>(resolve => { releaseFirstRequest = resolve; });
  await page.route(`${action}unsubscribe-request`, async intercepted => {
    if (intercepted.request().method() === 'OPTIONS') return intercepted.fulfill({ status: 204, headers: crossOrigin });
    if (++attempts === 1) {
      await holdFirstRequest;
      await intercepted.abort();
      return;
    }
    return intercepted.fulfill({ status: 202, headers: crossOrigin, json: { status: 'requested' } });
  });
  await page.clock.install();
  await page.goto(route);
  const form = page.getByRole('region', { name: 'Unsubscribe from the digest' });
  await page.getByRole('textbox', { name: 'Email' }).fill(address);
  const send = page.getByRole('button', { name: 'Send unsubscribe link' });
  await send.click();
  try {
    await expect.poll(() => attempts).toBe(1);
    await page.clock.fastForward(12_001);
    await expect(form.getByRole('alert')).toHaveText(requestError);
    await expect(send).toBeEnabled();
  } finally {
    releaseFirstRequest();
  }
  await send.click();
  await expect(page.getByRole('status')).toHaveText(genericReceipt);
});
