/**
 * Static pages — /about, /privacy, /terms, /status.
 *
 * Low-risk pages but still need to render + have the correct footer
 * links. Cheap coverage that catches regressions in `layout.tsx`.
 */
import { expect, test } from '@playwright/test';
import { waitForAppReady } from './utils/selectors';

const STATIC: { path: string; pattern: RegExp }[] = [
  { path: '/about', pattern: /About/i },
  { path: '/privacy', pattern: /Privacy/i },
  { path: '/terms', pattern: /Terms/i },
  { path: '/status', pattern: /Status|ETL|Ingestion/i },
];

test.describe('Static pages', () => {
  for (const { path, pattern } of STATIC) {
    test(`${path} — renders with a page heading matching ${pattern}`, async ({ page }) => {
      await page.goto(path);
      await waitForAppReady(page);
      await expect(page.getByRole('heading', { level: 1 })).toHaveText(pattern, { timeout: 15_000 });
    });
  }
});
