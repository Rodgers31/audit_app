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
    const kpiLabels = ['Budget', 'Execution', 'Total Debt', 'Pending Bills', 'Audit Issues', 'Stalled'];
    for (const label of kpiLabels) {
      await expect(
        page.locator('div').filter({ hasText: new RegExp(`^${label}$`) }).first()
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

  test('all six tabs are clickable and do not throw', async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on('pageerror', (err) => consoleErrors.push(err.message));

    const tabs = [
      countyTabs.overview,
      countyTabs.followTheMoney,
      countyTabs.budgetDebt,
      countyTabs.auditFindings,
      countyTabs.accountability,
      countyTabs.projects,
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
    // Scroll way down first so the footer is in view.
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    const beforeY = await page.evaluate(() => window.scrollY);
    expect(beforeY).toBeGreaterThan(300);

    await countyTabs.budgetDebt(page).click();
    // smooth scroll is ~300ms — poll until it settles
    await expect
      .poll(async () => page.evaluate(() => window.scrollY), { timeout: 3_000 })
      .toBeLessThan(beforeY);

    // The user should land above the page's total height, not at its end.
    const afterY = await page.evaluate(() => window.scrollY);
    const pageHeight = await page.evaluate(
      () => document.documentElement.scrollHeight - window.innerHeight
    );
    expect(afterY).toBeLessThan(pageHeight - 100);
  });

  test('Audit Findings tab renders without throwing', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (err) => errors.push(err.message));

    await countyTabs.auditFindings(page).click();

    // If `audit.findings` is undefined again, the tab will throw and this
    // locator will never resolve. Give it enough time to mount.
    await expect(page.locator('body')).toContainText(
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
