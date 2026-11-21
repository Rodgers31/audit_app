import { expect, test } from '@playwright/test';

const path = '/learn/auditor-general-guide';

test('opens from Learn and restores the addressed step through Previous, Back and reload', async ({ page }) => {
  await page.goto('/learn');
  await page.getByRole('link', { name: 'What the Auditor-General does' }).click();
  await expect(page).toHaveURL(path);
  const card = page.getByRole('article', { name: 'Who does the auditing?' });
  await expect(card.getByText('Step 1 of 4')).toBeVisible();
  await expect(card.getByRole('definition')).toHaveText('8 years');
  await expect(card.getByRole('link', { name: 'Previous' })).toHaveCount(0);
  await card.getByRole('link', { name: 'Next' }).press('Enter');

  const reporting = page.getByRole('article', { name: 'When must the Auditor-General report?' });
  const reportingHeading = reporting.getByRole('heading');
  await expect(page).toHaveURL(`${path}?step=reporting`);
  await expect(reportingHeading).toBeFocused();
  await expect(reporting.getByRole('definition')).toHaveText('6 months');
  await expect(reporting.getByText('Deadline after each financial year ends')).toBeVisible();
  await reporting.getByRole('link', { name: 'Next' }).press('Enter');
  const opinion = page.getByRole('article', { name: 'What does an audit report tell us?' });
  await expect(opinion.getByRole('heading')).toBeFocused();
  await opinion.getByRole('link', { name: 'Previous' }).press('Enter');
  await expect(reportingHeading).toBeFocused();
  await page.goBack();
  await expect(page).toHaveURL(`${path}?step=opinion`);
  await expect(opinion.getByRole('heading')).toBeFocused();
  await page.reload();
  await expect(opinion.getByRole('definition')).toHaveText('44 of 47');
  await opinion.getByRole('link', { name: 'Next' }).click();

  const action = page.getByRole('article', { name: 'Who acts on the report?' });
  await expect(action.getByRole('definition')).toHaveText('3 months');
  await expect(action.getByText('Deadline after the report is received')).toBeVisible();
  await action.getByRole('link', { name: 'Back to Learn' }).click();
  await expect(page).toHaveURL('/learn#auditor-general-path');
  await expect(page.getByRole('link', { name: 'What the Auditor-General does' })).toBeVisible();
});

test('links to the actual Article 229 reader and the dated OAG report table', async ({ page }) => {
  await page.goto(`${path}?step=opinion`);
  const card = page.getByRole('article', { name: 'What does an audit report tell us?' });
  await expect(card.getByText('Financial year ended 30 June 2025')).toBeVisible();
  await expect(card.getByRole('term')).toHaveText('County executive financial statements with a qualified opinion');
  await expect(card.getByRole('link', { name: /Office of the Auditor-General.*table 8, p\. 21/ })).toHaveAttribute('href',
    'https://libraryir.parliament.go.ke/server/api/core/bitstreams/e13a8fad-5b91-4ca2-bfa5-4d1d767be980/content#page=35');
  await card.getByRole('link', { name: 'Read Article 229' }).click();
  await expect(page).toHaveURL('/learn?article=229');
  const article = page.getByRole('article').filter({ has: page.getByRole('heading', { name: 'Auditor-General', exact: true }) });
  await expect(article.getByText('Art. 229', { exact: true })).toBeVisible();
  await expect(article.getByRole('link', { name: 'Audit findings', exact: true })).toBeVisible();
});

test('opens each existing AuditGava context from its guide step', async ({ page }) => {
  for (const [key, link, href] of [
    ['office', 'See what a government audit is', '/learn/glossary#term-audit'],
    ['reporting', 'See where AuditGava gets its reports', '/sources#sources-method'],
    ['opinion', 'Read audit findings', '/audits'],
    ['action', 'Open Nairobi’s audit tab', '/counties/nairobi?tab=audit'],
  ]) {
    await page.goto(`${path}?step=${key}`);
    await page.getByRole('link', { name: link, exact: true }).click();
    await expect(page).toHaveURL(href);
    if (key === 'office') {
      await expect(page.getByRole('button', { name: 'Government Audit', exact: true })).toHaveAttribute('aria-expanded', 'true');
    } else if (key === 'reporting') {
      await expect(page.getByRole('heading', { name: 'How this works', exact: true })).toBeVisible();
    } else if (key === 'opinion') {
      await expect(page.getByRole('heading', { name: 'Audit Findings', level: 1 })).toBeVisible();
    } else {
      await expect(page.getByRole('heading', { name: 'Nairobi County', level: 1 })).toBeVisible();
      await expect(page.getByRole('tab', { name: 'Audit', exact: true })).toHaveAttribute('aria-selected', 'true');
    }
  }
});

test.describe('touch and localized guide copy', () => {
  test.use({ hasTouch: true, reducedMotion: 'reduce', viewport: { width: 360, height: 800 } });

  test('supports touch Next in Kiswahili and the same named URL in plain English', async ({ page }) => {
    await page.addInitScript(() => {
      if (!localStorage.getItem('auditgava-lang')) localStorage.setItem('auditgava-lang', 'sw');
    });
    await page.goto(`${path}?step=unknown`);
    await expect(page.locator('html')).toHaveAttribute('lang', 'sw');
    const card = page.getByRole('article', { name: 'Nani hukagua fedha za umma?' });
    await expect(card.getByText('Hatua ya 1 kati ya 4')).toBeVisible();
    await card.getByRole('link', { name: 'Inayofuata' }).tap();
    const reporting = page.getByRole('article', { name: 'Mkaguzi Mkuu anapaswa kutoa ripoti lini?' });
    await expect(page).toHaveURL(`${path}?step=reporting`);
    await expect(reporting.getByRole('definition')).toHaveText('Miezi 6');
    await reporting.getByRole('link', { name: 'Inayofuata' }).tap();
    const opinion = page.getByRole('article', { name: 'Ripoti ya ukaguzi inatuambia nini?' });
    await expect(opinion.getByRole('definition')).toHaveText('44 kati ya 47');
    await expect(opinion.getByText(/pengo muhimu katika ushahidi wa ukaguzi/)).toBeVisible();
    await page.evaluate(() => localStorage.setItem('auditgava-lang', 'plain'));
    await page.reload();
    await expect(page).toHaveURL(`${path}?step=opinion`);
    const plain = page.getByRole('article', { name: 'What can I learn from an audit report?' });
    await expect(plain.getByRole('definition')).toHaveText('44 out of 47');
    await expect(plain.getByText(/an important gap in the evidence needed to check them/)).toBeVisible();
  });
});
