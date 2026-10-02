import { expect, test, type Page } from '@playwright/test';

async function glossary(page: Page) {
  await page.goto('/learn/glossary');
  await expect(page.getByRole('searchbox', { name: 'Search glossary' })).toBeVisible();
}
async function quiz(page: Page) {
  await page.goto('/learn/quiz');
  await page.getByRole('button', { name: /Public Finance/ }).click();
  await expect(page.getByText('1/6', { exact: true })).toBeVisible();
}

test.describe('Learn Page', () => {
  test('learn page loads successfully', async ({ page }) => {
    await page.goto('/learn');
    await expect(page.getByRole('heading', { name: 'Learning Hub', exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: /229\s*Auditor-General/ })).toBeVisible();
  });
  test('learn page has search functionality', async ({ page }) => {
    await page.goto('/learn');
    await page.getByRole('searchbox', { name: 'Search civic topics or the Constitution' }).fill('Article 214');
    await page.getByRole('button', { name: 'Search', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Public debt', exact: true })).toBeVisible();
  });
  test('learn page has interactive sections', async ({ page }) => {
    await page.goto('/learn');
    for (const path of ['/learn/glossary', '/learn/quiz', '/learn/government', '/learn/why-it-matters']) {
      await expect(page.locator(`main a[href="${path}"]`)).toBeVisible();
    }
  });
});

test.describe('Interactive Glossary', () => {
  test('glossary terms are visible', async ({ page }) => {
    await glossary(page);
    await expect(page.getByText('12 terms across 6 themes', { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: /^National Debt/ })).toBeVisible();
  });
  test('glossary term cards are clickable', async ({ page }) => {
    await glossary(page);
    await page.getByRole('button', { name: /^National Debt/ }).click();
    await expect(page.getByText(/Article 214/).first()).toBeVisible();
    await expect(page.getByText('In plain life', { exact: true }).first()).toBeVisible();
  });
  test('glossary category filter works', async ({ page }) => {
    await glossary(page);
    await page.getByRole('button', { name: /Accountability\s*3/ }).click();
    await expect(page.getByRole('button', { name: /^Government Audit/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /^National Debt/ })).toHaveCount(0);
    await expect(page.getByText(/3 terms/).last()).toBeVisible();
  });
  test('glossary search filters terms', async ({ page }) => {
    await glossary(page);
    await page.getByRole('searchbox', { name: 'Search glossary' }).fill('no-such-synthetic-term');
    await expect(page.getByRole('heading', { name: 'No matches', exact: true })).toBeVisible();
    await page.getByRole('searchbox', { name: 'Search glossary' }).fill('National Debt');
    await expect(page.getByRole('button', { name: /^National Debt/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /^Government Audit/ })).toHaveCount(0);
  });
});

test.describe('Explainer Videos', () => {
  // No video gallery/modal/category controls are mounted on the current Learn
  // routes. Track each original unsupported case explicitly under #291.
  test.fixme('video cards are displayed', async () => {});
  test.fixme('clicking video card opens modal', async () => {});
  test.fixme('video category filter works', async () => {});
});

test.describe('Engagement Quiz', () => {
  test('quiz section is visible', async ({ page }) => {
    await page.goto('/learn/quiz');
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Quiz Games');
    await expect(page.getByRole('button', { name: /Public Finance/ })).toBeVisible();
  });
  test('quiz cards are interactive', async ({ page }) => {
    await quiz(page);
    await expect(page.locator('main button').filter({ hasText: /^A/ })).toHaveCount(1);
  });
  test('quiz can be navigated through questions', async ({ page }) => {
    await quiz(page);
    await page.locator('main button').filter({ hasText: /^A/ }).click();
    await page.getByRole('button', { name: /Next Question/i }).click();
    await expect(page.getByText('2/6', { exact: true })).toBeVisible();
  });
  test('quiz shows results after completion', async ({ page }) => {
    await quiz(page);
    for (let n = 1; n <= 6; n++) {
      await expect(page.getByText(`${n}/6`, { exact: true })).toBeVisible();
      await page.locator('main button').filter({ hasText: /^A/ }).click();
      await page.getByRole('button', { name: /Next Question|See Results/i }).click();
    }
    await expect(page.getByRole('heading', { name: 'Review Answers', exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: /Play Again/i })).toBeVisible();
  });
});

test.describe('Why This Matters Section', () => {
  test('stories section is visible', async ({ page }) => {
    await page.goto('/learn/why-it-matters');
    await expect(page.getByRole('heading', { name: 'Your Money, Your Life', exact: true })).toBeVisible();
    await expect(page.getByText(/Healthcare: Whether hospitals have medicine/)).toBeVisible();
  });
  // Current stories/action steps are static prose. Clicking arbitrary buttons
  // never exercised expansion or an action. Named quarantine under #291.
  test.fixme('story cards can be expanded', async () => {});
  test.fixme('action steps are interactive', async () => {});
});

test.describe('Learn Page Accessibility', () => {
  test('learn page is keyboard navigable', async ({ page }) => {
    await page.goto('/learn');
    await page.keyboard.press('Tab');
    await expect(page.getByRole('link', { name: 'Skip to main content' })).toBeFocused();
  });
  test('learn page has proper headings structure', async ({ page }) => {
    // Learn currently keeps English copy in all three supported language modes.
    // Check the real hierarchy without inventing unreviewed translations.
    await page.goto('/learn');
    for (const name of ['EN', 'SW', 'Aa']) {
      const language = page.getByRole('radio', { name, exact: true });
      await language.click();
      await expect(language).toHaveAttribute('aria-checked', 'true');
      await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1);
      await expect(page.getByRole('heading', { level: 1 })).toHaveText('Learning Hub');
      await expect(page.getByRole('heading', { level: 2, name: 'Understand Kenya’s money, law & power' })).toBeVisible();
      for (const name of ['The Constitution, as a book you can actually read', 'Keep learning', 'Popular questions', 'Ready to put your knowledge to use?']) {
        await expect(page.getByRole('heading', { level: 2, name, exact: true })).toBeVisible();
      }
      await expect(page.getByRole('heading', { level: 3, name: 'Read the law that shapes every shilling' })).toBeVisible();
      await expect(page.getByRole('heading', { level: 3, name: 'Civic quiz', exact: true })).toBeVisible();
      await expect(page.getByRole('searchbox', { name: 'Search civic topics or the Constitution' })).toBeVisible();
    }
  });
});
