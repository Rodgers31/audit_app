import { expect, test } from '@playwright/test';

for (const viewport of [{ width: 1365, height: 900 }, { width: 390, height: 844 }]) {
  test(`reset auth loading keeps the footer below the viewport at ${viewport.width}px`, async ({ page, context }) => {
    await page.setViewportSize(viewport);
    const actor = '00000000-0000-4000-8000-000000000001';
    const encode = (value: unknown) => Buffer.from(JSON.stringify(value)).toString('base64url');
    const expires = Math.floor(Date.now() / 1000) + 3600;
    const token = `${encode({ alg: 'HS256', typ: 'JWT' })}.${encode({ sub: actor, exp: expires })}.inert`;
    await context.addCookies([{ name: 'sb-127-auth-token', domain: '127.0.0.1', path: '/',
      value: 'base64-' + encode({ access_token: token, refresh_token: 'inert-local-refresh',
        expires_at: expires, expires_in: 3600, token_type: 'bearer',
        user: { id: actor, email: 'local@example.invalid', aud: 'authenticated', role: 'authenticated', app_metadata: {}, user_metadata: {} } }) }]);
    let release!: () => void;
    const pending = new Promise<void>(resolve => { release = resolve; });
    let sawProfile!: () => void;
    const profileRequested = new Promise<void>(resolve => { sawProfile = resolve; });
    await page.route('**/*', async route => {
      const url = new URL(route.request().url());
      if (!['127.0.0.1', 'localhost'].includes(url.hostname)) return route.abort();
      if (url.pathname === '/rest/v1/profiles') {
        sawProfile();
        await pending;
      }
      return route.continue();
    });
    try {
      await page.goto('/reset-password?recovery=inert-local-code', { waitUntil: 'domcontentloaded' });
      await profileRequested;
      await expect(page.locator('main .animate-spin')).toBeVisible();
      const footer = await page.locator('footer').boundingBox();
      expect(footer).not.toBeNull();
      expect(footer!.y).toBeGreaterThanOrEqual(viewport.height);
    } finally {
      release();
    }
    await expect(page.getByRole('heading', { name: 'Choose a New Password' })).toBeVisible();
    const footer = await page.locator('footer').boundingBox();
    expect(footer!.y).toBeGreaterThanOrEqual(viewport.height);
  });
}
