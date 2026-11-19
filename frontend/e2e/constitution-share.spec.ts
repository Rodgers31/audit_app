import { expect, test, type Page } from '@playwright/test';

type ShareTestWindow = typeof window & {
  recordCopiedArticle: (url: string) => Promise<void>;
  recordNativeArticle: (data: ShareData) => Promise<void>;
  failNativeArticle: () => void;
};

async function openReader(page: Page) {
  await page.goto('/learn?article=229&from=budget#constitution-book');
  await expect(page.getByRole('heading', { name: 'Auditor-General', exact: true })).toBeVisible();
  return page.getByRole('region', { name: 'Constitution of Kenya reader' });
}

test('copies the active canonical article link and preserves the reader mode and history', async ({ page }) => {
  const copied: string[] = [];
  await page.exposeFunction('recordCopiedArticle', (url: string) => { copied.push(url); });
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: (url: string) => (window as ShareTestWindow).recordCopiedArticle(url) },
    });
  });
  const reader = await openReader(page);
  await reader.getByRole('radio', { name: 'Official text' }).press('Space');
  const share = reader.getByRole('button', { name: 'Share', exact: true });
  await share.press('Enter');
  const origin = new URL(page.url()).origin;
  await expect(reader.getByRole('status')).toHaveText('Link copied');
  expect(copied).toEqual([`${origin}/learn?article=229`]);
  await expect(share).toBeFocused();
  await expect(reader.getByRole('dialog')).toHaveCount(0);
  await expect(reader.getByRole('radio', { name: 'Official text' })).toBeChecked();
  await expect(page).toHaveURL(/article=229&from=budget#constitution-book$/);

  await reader.getByRole('button', { name: 'Art. 230', exact: true }).click();
  await expect(reader.getByRole('status')).toBeEmpty();
  await share.click();
  await expect(reader.getByRole('status')).toHaveText('Link copied');
  expect(copied.at(-1)).toBe(`${origin}/learn?article=230`);
  await page.goBack();
  await expect(reader.getByRole('heading', { name: 'Auditor-General', exact: true })).toBeVisible();
  await expect(reader.getByRole('radio', { name: 'Official text' })).toBeChecked();
});

test.describe('touch reader sharing', () => {
  test.use({ hasTouch: true, viewport: { width: 360, height: 840 } });

  test('uses native sharing and leaves the reader alone when the prompt is cancelled', async ({ page }) => {
    const shares: ShareData[] = [];
    await page.exposeFunction('recordNativeArticle', (data: ShareData) => { shares.push(data); });
    await page.addInitScript(() => {
      let attempt = 0;
      Object.defineProperty(navigator, 'share', {
        configurable: true,
        value: async (data: ShareData) => {
          await (window as ShareTestWindow).recordNativeArticle(data);
          if (++attempt === 1) throw new DOMException('Cancelled', 'AbortError');
        },
      });
    });
    const reader = await openReader(page);
    const share = reader.getByRole('button', { name: 'Share', exact: true });
    const expected = {
      title: 'Art. 229 · Auditor-General',
      url: `${new URL(page.url()).origin}/learn?article=229`,
    };
    await share.tap();
    await expect.poll(() => shares).toEqual([expected]);
    await expect(reader.getByRole('dialog')).toHaveCount(0);
    await expect(reader.getByRole('status')).toBeEmpty();
    await expect(share).toBeFocused();
    await share.tap();
    await expect.poll(() => shares).toEqual([expected, expected]);
    await expect(reader.getByRole('dialog')).toHaveCount(0);
  });

  test('makes the exact link selectable when copying fails and restores focus on close', async ({ page }) => {
    await page.addInitScript(() => {
      Object.defineProperty(navigator, 'share', { configurable: true, value: undefined });
      Object.defineProperty(navigator, 'clipboard', {
        configurable: true,
        value: { writeText: async () => { throw new DOMException('Denied', 'NotAllowedError'); } },
      });
    });
    const reader = await openReader(page);
    const share = reader.getByRole('button', { name: 'Share', exact: true });
    await share.tap();
    const sheet = reader.getByRole('dialog', { name: 'Share this article' });
    const link = sheet.getByRole('textbox', { name: 'Article link' });
    const url = `${new URL(page.url()).origin}/learn?article=229`;
    await expect(link).toHaveValue(url);
    await expect(link).toHaveAttribute('readonly', '');
    await sheet.getByRole('button', { name: 'Copy link' }).tap();
    await expect(sheet.getByRole('status')).toHaveText('Copy the selected link using your device.');
    await expect(link).toBeFocused();
    expect(await link.evaluate((field: HTMLInputElement) =>
      field.value.slice(field.selectionStart ?? 0, field.selectionEnd ?? 0))).toBe(url);
    await sheet.getByRole('button', { name: 'Close', exact: true }).focus();
    await page.keyboard.press('ArrowRight');
    await expect(page).toHaveURL(/article=229&from=budget#constitution-book$/);
    await page.keyboard.press('Escape');
    await expect(sheet).toBeHidden();
    await expect(share).toBeFocused();
  });

  test('a rejected native share cannot open a sheet for an article the reader has left', async ({ page }) => {
    await page.addInitScript(() => {
      Object.defineProperty(navigator, 'share', {
        configurable: true,
        value: () => new Promise((_, reject) => {
          (window as ShareTestWindow).failNativeArticle = () => reject(new DOMException('Unavailable', 'NotAllowedError'));
        }),
      });
    });
    const reader = await openReader(page);
    await reader.getByRole('button', { name: 'Share', exact: true }).tap();
    await page.waitForFunction(() => typeof (window as ShareTestWindow).failNativeArticle === 'function');
    await reader.getByRole('button', { name: 'Art. 230', exact: true }).tap();
    await expect(reader.getByRole('heading', { name: 'Salaries and Remuneration Commission' })).toBeVisible();
    await page.evaluate(() => { (window as ShareTestWindow).failNativeArticle(); });
    await expect(reader.getByRole('dialog')).toHaveCount(0);
    await reader.getByRole('button', { name: 'Share', exact: true }).tap();
    await page.evaluate(() => { (window as ShareTestWindow).failNativeArticle(); });
    await expect(reader.getByRole('textbox', { name: 'Article link' })).toHaveValue(
      `${new URL(page.url()).origin}/learn?article=230`,
    );
  });
});
