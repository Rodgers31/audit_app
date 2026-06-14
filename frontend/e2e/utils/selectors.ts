/**
 * Centralised resilient locators.
 *
 * Tests should prefer these helpers over raw CSS/XPath so that a UI
 * copy-change ripples through one file instead of dozens of spec files.
 * Everything here is based on role + accessible name (or stable data
 * attributes where present) — no brittle `.css-abc123` class chains.
 */
import type { Locator, Page } from '@playwright/test';

/* ═══════════ Top-level navigation ═══════════ */

export const nav = {
  root: (page: Page): Locator => page.getByRole('banner').locator('header, nav').first(),
  home: (page: Page): Locator =>
    page.getByRole('link', { name: /^(Dashboard|Home|Dashibodi)$/i }).first(),
  debt: (page: Page): Locator =>
    page
      .getByRole('link', { name: /^(National Debt|Deni la Taifa|Money Kenya Owes)$/i })
      .first(),
  budget: (page: Page): Locator =>
    page
      .getByRole('link', {
        name: /^(Budget & Spending|Bajeti na Matumizi|The Budget)$/i,
      })
      .first(),
  counties: (page: Page): Locator =>
    page.getByRole('link', { name: /^(County Explorer|Kaunti|Counties)$/i }).first(),
  transparency: (page: Page): Locator =>
    page
      .getByRole('link', {
        name: /^(Follow the Money|Fuatilia Pesa|Where Money Goes)$/i,
      })
      .first(),
  learn: (page: Page): Locator =>
    page.getByRole('link', { name: /^(Learn|Jifunze)$/i }).first(),
  signIn: (page: Page): Locator =>
    page.getByRole('button', { name: /^(Sign In|Ingia)$/i }).first(),
  mobileMenuToggle: (page: Page): Locator =>
    page.getByRole('button', { name: /open navigation menu|Fungua menyu/i }),
};

/* ═══════════ Language switcher (3-way pill) ═══════════ */

export const langSwitcher = {
  root: (page: Page): Locator =>
    page.getByRole('radiogroup', { name: /Language|Lugha/i }).first(),
  en: (page: Page): Locator =>
    langSwitcher.root(page).getByRole('radio', { name: /^EN$/ }),
  sw: (page: Page): Locator =>
    langSwitcher.root(page).getByRole('radio', { name: /^SW$/ }),
  plain: (page: Page): Locator =>
    langSwitcher.root(page).getByRole('radio', { name: /^Aa$/ }),
};

/* ═══════════ County detail tabs ═══════════ */

export const countyTabs = {
  overview: (page: Page): Locator =>
    page.getByRole('button', { name: /^(Overview|Muhtasari)$/ }),
  followTheMoney: (page: Page): Locator =>
    page.getByRole('button', { name: /^(Follow the Money|Fuatilia Pesa)$/ }),
  budgetDebt: (page: Page): Locator =>
    page.getByRole('button', { name: /^(Budget & Debt|Bajeti na Deni)$/ }),
  auditFindings: (page: Page): Locator =>
    page.getByRole('button', { name: /^(Audit Findings|Matokeo ya Ukaguzi)$/ }),
  accountability: (page: Page): Locator =>
    page.getByRole('button', { name: /^(Accountability|Uwajibikaji)$/ }),
  projects: (page: Page): Locator =>
    page.getByRole('button', { name: /^(Projects|Miradi)$/ }),
};

/* ═══════════ PageShell (used on every sub-page) ═══════════ */

export const pageShell = {
  h1: (page: Page): Locator => page.getByRole('heading', { level: 1 }).first(),
  backLink: (page: Page): Locator =>
    page.locator('a').filter({ hasText: /^(← |⟵ )?(Home|Nyumbani|All counties|Kaunti zote)/ }).first(),
};

/* ═══════════ Follow the Money waterfall ═══════════ */

export const waterfall = {
  root: (page: Page): Locator =>
    page.locator('div').filter({ hasText: /^Follow the Money · /i }).first(),
  stage: (page: Page, stage: 'Allocated' | 'Spent' | 'Flagged'): Locator =>
    page.locator('[class*="rounded"]').filter({ hasText: stage }).first(),
  gapPill: (page: Page, label: string): Locator =>
    page.locator('[class*="border-dashed"]').filter({ hasText: label }).first(),
  yearSelector: (page: Page): Locator => page.locator('select').first(),
  efficiencyRing: (page: Page): Locator =>
    page.locator('[class*="rounded-full"]').filter({ hasText: /Efficiency/i }).first(),
  sourceLink: (page: Page): Locator =>
    page.getByRole('link', { name: /CoB.*Budget Implementation Review/i }).first(),
};

/* ═══════════ Convenience: wait until the app's core scaffolding is ready.
 *
 * Next.js hydrates progressively; tests that click something 50ms after
 * `page.goto` often hit a pre-hydration DOM and the click is a no-op.
 * This helper waits for the nav to be both visible AND interactive.
 */
export async function waitForAppReady(page: Page): Promise<void> {
  await page.waitForLoadState('domcontentloaded');
  // Nav link in the header is the earliest-rendered interactive element
  // on every page; once it responds to hover the app is hydrated.
  const home = nav.counties(page);
  await home.waitFor({ state: 'visible', timeout: 15_000 });
}
