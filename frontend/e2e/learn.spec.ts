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
    await expect(page).toHaveURL(/article=214/);
    await page.goBack();
    await expect(page.getByRole('heading', { name: 'Auditor-General', exact: true })).toBeVisible();
    await page.goForward();
    await expect(page.getByRole('heading', { name: 'Public debt', exact: true })).toBeVisible();
  });
  test('learn page has interactive sections', async ({ page }) => {
    await page.goto('/learn');
    for (const path of ['/learn/glossary', '/learn/quiz', '/learn/government', '/learn/why-it-matters']) {
      await expect(page.locator(`main a[href="${path}"]`)).toBeVisible();
    }
  });
  test('article links, browser history and the reading preference work together', async ({ page }) => {
    await page.goto('/learn?article=229');
    const reader = page.getByRole('region', { name: 'Constitution of Kenya reader' });
    await expect(reader.getByRole('heading', { name: 'Auditor-General', exact: true })).toBeVisible();
    const plain = reader.getByRole('radio', { name: 'Plain English' });
    const official = reader.getByRole('radio', { name: 'Official text' });
    await expect(plain).toBeChecked();
    await expect(reader.getByRole('progressbar')).toHaveAccessibleName('2 articles left in Chapter 12');
    await expect(reader.getByRole('link', { name: 'Audit findings', exact: true })).toHaveAttribute('href', '/audits');
    await plain.focus();
    await page.keyboard.press('ArrowRight');
    await expect(official).toBeChecked();
    await expect(reader.getByRole('link', { name: /Authoritative text from Kenya Law/ })).toBeVisible();
    await expect(page).toHaveURL(/article=229/);
    await reader.getByRole('button', { name: 'Article 251', exact: true }).click();
    await expect(page).toHaveURL(/article=251/);
    await reader.getByRole('button', { name: 'Back to Article 229', exact: true }).click();
    await expect(reader.getByRole('heading', { name: 'Auditor-General', exact: true })).toBeVisible();
    await reader.getByRole('button', { name: 'Art. 230', exact: true }).click();
    await expect(page).toHaveURL(/article=230/);
    await expect(reader.getByRole('heading', { name: 'Salaries and Remuneration Commission' })).toBeVisible();
    await page.goBack();
    await expect(reader.getByRole('heading', { name: 'Auditor-General', exact: true })).toBeVisible();
    await page.goForward();
    await expect(reader.getByRole('heading', { name: 'Salaries and Remuneration Commission' })).toBeVisible();
    await page.reload();
    await expect(official).toBeChecked();
  });

  test('mobile reader controls have names and the chapter drawer restores focus', async ({ browser }) => {
    const context = await browser.newContext({ hasTouch: true, viewport: { width: 360, height: 840 } });
    try {
      const page = await context.newPage();
      await page.goto('/learn?article=229');
      await expect(page.getByRole('button', { name: 'Search', exact: true })).toBeVisible();
      const reader = page.getByRole('region', { name: 'Constitution of Kenya reader' });
      const chapters = reader.getByRole('button', { name: 'Chapters', exact: true });
      const drawer = reader.getByRole('navigation', { name: 'Chapters' });
      await chapters.tap();
      await expect(drawer).toBeVisible();
      await drawer.getByRole('button', { name: /229\s*Auditor-General/ }).focus();
      await page.keyboard.press('Escape');
      await expect(drawer).toBeHidden();
      await expect(chapters).toBeFocused();
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(360);
      await page.goto('/learn?article=215');
      await expect(reader.getByRole('radio', { name: 'Official text' })).toBeChecked();
      await expect(reader.getByRole('radio', { name: 'Plain English' })).toBeDisabled();
      await expect(reader.getByText('A plain-English summary is unavailable for this article.')).toBeVisible();
    } finally {
      await context.close();
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
    await expect(page.getByText('In plain life', { exact: true }).first()).toBeVisible();
    await page.getByRole('link', { name: /Article 214.*Public debt/i }).click();
    await expect(page).toHaveURL(/\/learn\?article=214/);
    await expect(page.getByRole('heading', { name: 'Public debt', exact: true })).toBeVisible();
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
    await page.goto('/learn');
    await page.locator('header summary').filter({ hasText: /^Language$/ }).click();
    const languagePicker = page.locator('header').getByRole('radiogroup');
    for (const name of ['English', 'Kiswahili', 'Plain English']) {
      const language = languagePicker.getByRole('radio', { name, exact: true });
      await language.check();
      await expect(language).toBeChecked();
      await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1);
      await expect(page.getByRole('heading', { level: 1 })).toHaveText('Learning Hub');
      await expect(page.getByRole('heading', { level: 2, name: 'Understand Kenya’s money, law & power' })).toBeVisible();
      for (const name of ['The Constitution, as a book you can actually read', 'Keep learning', 'Popular questions', 'Ready to put your knowledge to use?']) {
        await expect(page.getByRole('heading', { level: 2, name, exact: true })).toBeVisible();
      }
      const readerHeading = name === 'Kiswahili'
        ? 'Soma sheria inayoongoza matumizi ya kila shilingi'
        : 'Read the law that shapes every shilling';
      await expect(page.getByRole('heading', { level: 3, name: readerHeading })).toBeVisible();
      await expect(page.getByRole('heading', { level: 3, name: 'Civic quiz', exact: true })).toBeVisible();
      await expect(page.getByRole('searchbox', { name: 'Search civic topics or the Constitution' })).toBeVisible();
    }
  });
});
