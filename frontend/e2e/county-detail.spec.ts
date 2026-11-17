/**
 * County Detail (/counties/[id])
 *
 * Guards against regressions surfaced between v1.1.0–v1.1.2:
 *   - AuditTab crash (`audit.findings is not iterable`)
 *   - Budget & Debt tab landing on the footer instead of tab bar
 *   - Follow the Money showing "no data for this period"
 *   - /counties/[id] taking 5 s cold due to compounded SSR timeouts
 */
import { expect, test } from '@playwright/test';
import type { AccountabilityScorecard, GradeFactor } from '../types';
import { countyTabs, waitForAppReady } from './utils/selectors';

const COUNTY_ID = '001'; // Nairobi — widest data coverage across FYs

test.describe('/counties/[id] — hero', () => {
  test('renders county name, KPIs, and both grade badges', async ({ page }) => {
    await page.goto(`/counties/${COUNTY_ID}`);
    await waitForAppReady(page);

    await expect(page.getByRole('heading', { level: 1 })).toContainText(
      /Nairobi County|Mombasa County|Kaunti/i
    );

    // Quick KPI strip — labels are static, values render post-hydrate
    const kpiLabels = ['Budget', 'Execution', 'Total Debt', 'Pending Bills', 'Audit Issues'];
    for (const label of kpiLabels) {
      await expect(
        page.getByText(label, { exact: true }).first()
      ).toBeVisible({ timeout: 15_000 });
    }

    // HEALTH + AUDIT grade badges
    await expect(page.locator('text=/HEALTH/i').first()).toBeVisible();
    await expect(page.locator('text=/AUDIT/i').first()).toBeVisible();
  });
});

test.describe('/counties/[id] — tabs', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`/counties/${COUNTY_ID}`);
    await waitForAppReady(page);
  });

  test('all five published tabs are clickable and do not throw', async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on('pageerror', (err) => consoleErrors.push(err.message));

    const tabs = [
      countyTabs.overview,
      countyTabs.followTheMoney,
      countyTabs.budgetDebt,
      countyTabs.auditFindings,
      countyTabs.accountability,
    ];
    for (const tab of tabs) {
      await tab(page).click();
      await page.waitForTimeout(400); // let motion.div transition settle
      // Any tab that throws during render will populate consoleErrors.
    }

    // Regression guard for the v1.1.1 AuditTab crash:
    expect(consoleErrors.filter((e) => /audit\.findings is not iterable/.test(e))).toEqual([]);
    // Broader sanity: no unhandled TypeErrors from any tab
    expect(consoleErrors.filter((e) => /TypeError/.test(e))).toEqual([]);
  });

  test('clicking Budget & Debt scrolls to the tab bar, not the footer', async ({ page }) => {
    await expect(page.getByText('Budget', { exact: true }).first()).toBeVisible();
    // Scroll way down first so the footer is in view.
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(300);
    const beforeY = await page.evaluate(() => window.scrollY);
    expect(beforeY).toBeGreaterThan(300);

    await countyTabs.budgetDebt(page).click();
    const panel = page.getByRole('tabpanel', { name: 'Budget' });
    await expect(panel.getByRole('heading', { name: /Budget Summary/i })).toBeVisible();
    const sticky = page.getByRole('tablist', { name: 'Explore this county' }).locator('..');
    const banner = page.getByRole('banner');
    await expect.poll(async () => {
      const header = (await banner.boundingBox())!;
      const anchorTop = await sticky.evaluate((element) => (
        element.previousElementSibling!.getBoundingClientRect().top
      ));
      return Math.abs(anchorTop - (header.y + header.height));
    }).toBeLessThanOrEqual(1);
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBeLessThan(beforeY - 100);
  });

  test('Audit Findings tab renders without throwing', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (err) => errors.push(err.message));

    await countyTabs.auditFindings(page).click();

    // If `audit.findings` is undefined again, the tab will throw and this
    // locator will never resolve. Give it enough time to mount.
    await expect(page.getByRole('tabpanel', { name: 'Audit' })).toContainText(
      /Audit Findings|Matokeo ya Ukaguzi|by_severity|Findings/i,
      { timeout: 10_000 }
    );
    expect(errors).toEqual([]);
  });
});

test.describe('/counties/[id] — performance budget', () => {
  test('page transitions feel instant on warm cache', async ({ page }) => {
    // Prime the cache with a first visit
    await page.goto(`/counties/${COUNTY_ID}`);
    await waitForAppReady(page);

    // Navigate away + back; the second visit should hit React Query cache.
    await page.goto('/counties');
    await waitForAppReady(page);

    const t0 = Date.now();
    await page.goto(`/counties/${COUNTY_ID}`);
    await waitForAppReady(page);
    const elapsed = Date.now() - t0;

    // Soft perf assertion — warm SSR + hydrated React Query should land
    // well under 3 s even on a slow CI runner. If this fails we know
    // the SSR-timeout regression is back.
    expect(elapsed).toBeLessThan(3_000);
  });
});

test.describe('/counties/[id] — accountability factor layout', () => {
  test.use({ reducedMotion: 'reduce' });

  const impacts = [
    ['major', 'Major'],
    ['moderate', 'Moderate'],
    ['minor', 'Minor'],
  ] as const;

  for (const width of [320, 360]) {
    test(`keeps impact labels on one line with long details at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      const factors: GradeFactor[] = impacts.map(([impact, caption], index) => ({
        impact,
        label: `Synthetic ${caption.toLowerCase()} factor`,
        detail: `AuditReconciliationReference2025Edition${index} requires supporting records before this finding can be reconciled.`,
        points: -(index + 1),
      }));
      await page.route(`**/api/v1/counties/${COUNTY_ID}/accountability`, async (route) => {
        const response = await route.fetch();
        expect(response.ok()).toBe(true);
        const scorecard: AccountabilityScorecard = await response.json();
        await route.fulfill({ response, json: { ...scorecard, grade_factors: factors } });
      });

      await page.goto(`/counties/${COUNTY_ID}`);
      await waitForAppReady(page);
      await countyTabs.accountability(page).click();
      await expect(page.getByRole('heading', { name: 'How this grade was calculated' })).toBeVisible();
      await page.evaluate(() => document.fonts.ready);

      for (let index = 0; index < factors.length; index++) {
        const factor = factors[index];
        const detail = page.getByText(factor.detail, { exact: true });
        const row = detail.locator('..');
        await expect(detail).toBeVisible();
        const chip = row.getByText(impacts[index][1], { exact: true });
        const geometry = await chip.evaluate((label) => {
          const description = label.nextElementSibling!;
          const lineCount = (element: Element) => {
            const range = document.createRange();
            range.selectNodeContents(element);
            return new Set(Array.from(range.getClientRects(), ({ top }) => Math.round(top))).size;
          };
          const rowBounds = label.parentElement!.getBoundingClientRect();
          const descriptionBounds = description.getBoundingClientRect();
          return {
            labelLines: lineCount(label),
            labelFits: label.scrollWidth <= label.clientWidth,
            detailLines: lineCount(description),
            detailFits: descriptionBounds.right <= rowBounds.right + 1
              && description.scrollWidth <= description.clientWidth,
          };
        });
        expect.soft(geometry.labelLines, `${impacts[index][1]} label at ${width}px`).toBe(1);
        expect.soft(geometry.labelFits).toBe(true);
        expect.soft(geometry.detailLines).toBeGreaterThan(1);
        expect.soft(geometry.detailFits).toBe(true);
      }
    });
  }
});
