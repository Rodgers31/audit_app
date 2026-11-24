import { expect, test } from '@playwright/test';

test('budget page filter toggles and chart renders', async ({ page }) => {
  await page.goto('/budget');
  await expect(page.getByRole('heading', { name: 'KES 180B approved for FY 2025/26' })).toBeVisible();
  await expect(page.getByText('Spending & net lending KES 150B', { exact: true })).toBeVisible();
  await expect(page.getByText('Tax revenue', { exact: true }).first().locator('..')).toContainText('80B');
  await expect(page.getByRole('button', { name: 'Explore Where it goes', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'FY2024/25', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'KES 150B approved for FY 2024/25' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'KES 180B approved for FY 2025/26' })).toHaveCount(0);
});

test.describe('Budget segmented flow', () => {
  test.use({ hasTouch: true, viewport: { width: 360, height: 820 }, reducedMotion: 'reduce' });

  test('opens the same exact values by touch, hover and keyboard and clears selection', async ({ page }) => {
    await page.goto('/budget');
    const uses = page.getByRole('region', { name: 'Where it goes' });
    const bar = uses.getByRole('button', { name: 'Explore Where it goes', exact: true });
    const readout = uses.locator('[aria-live=polite]');
    const legend = uses.getByRole('button', { name: 'Interest on debt KES 30B' });
    await expect(bar).toBeVisible();
    const bounds = (await bar.boundingBox())!;
    const interest = { x: bounds.width * 0.1, y: bounds.height / 2 };
    await bar.tap({ position: interest });
    await expect(readout).toHaveText('Interest on debt · KES 30,000,000,000 · 20%');
    await expect(legend).toHaveAttribute('aria-pressed', 'true');
    await bar.tap({ position: interest });
    await expect(legend).toHaveAttribute('aria-pressed', 'false');
    await expect(readout).toBeEmpty();
    await bar.tap({ position: interest });
    await uses.getByRole('heading', { name: 'Where it goes' }).tap();
    await expect(readout).toBeEmpty();

    await bar.hover({ position: interest });
    await expect(readout).toHaveText('Interest on debt · KES 30,000,000,000 · 20%');
    await legend.focus();
    await expect(legend).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(legend).toHaveAttribute('aria-pressed', 'true');
    await page.keyboard.press('Escape');
    await expect(readout).toBeEmpty();
    await expect(legend).toHaveAttribute('aria-pressed', 'false');

    await bar.focus();
    await page.keyboard.press('End');
    await expect(readout).toContainText('Counties');
    await page.keyboard.press('Home');
    await expect(readout).toContainText('Interest on debt');
    await uses.getByText('Read chart data', { exact: true }).tap();
    await expect(uses.getByRole('row', { name: /Interest on debt/ })).toContainText('KES 30,000,000,000 · 20%');
    await expect(page.getByRole('heading', { name: /budget, visualised/i })).toHaveCount(0);

    await page.getByRole('button', { name: 'FY2024/25', exact: true }).tap();
    await expect(page.getByRole('heading', { name: 'KES 150B approved for FY 2024/25' })).toBeVisible();
    await expect(uses.getByRole('table')).toHaveCount(0);
    await expect(readout).toBeEmpty();
  });
});

test('Budget trend cards and Treasury callout fit their content boxes', async ({ page }, testInfo) => {
  const screenshotStyle = 'header.fixed, nextjs-portal { visibility: hidden; }';
  // The public fixture has two SSR fiscal periods. Age only this browser’s
  // cache so the fiscal query fetches the longer history below.
  await page.clock.setFixedTime(Date.now() + 2 * 60 * 60 * 1000);
  await page.route('**/api/v1/fiscal/summary', async route => {
    const response = await route.fetch();
    const json = await response.json();
    const older = ([
      ['FY 2019/20', 72, 'Actual'],
      ['FY 2020/21', 90, 'Approved'],
      ['FY 2021/22', 100, 'Actual'],
      ['FY 2022/23', 120, 'Preliminary'],
      ['FY 2023/24', 140, 'Supplementary I'],
    ] as const).map(([fiscal_year, amount, vintage]) => {
      const first = json.history[0];
      const revenue = fiscal_year === 'FY 2023/24' ? null : amount * 0.8e9;
      const proof = (measure: string, value: number | null) => ({
        ...first.measure_qualifications[measure],
        fiscal_year, value_kes: value, vintage,
        source: {
          ...first.measure_qualifications[measure].source,
          title: 'Synthetic history report on government revenue and spending', column: vintage,
        },
      });
      return {
        ...first,
        fiscal_year,
        appropriated_budget: amount * 1e9,
        total_revenue: revenue,
        split_basis: ['FY 2020/21', 'FY 2022/23'].includes(fiscal_year) ? null : first.split_basis,
        measure_qualifications: {
          appropriated_budget: proof('appropriated_budget', amount * 1e9),
          total_revenue: proof('total_revenue', revenue),
          total_borrowing: proof('total_borrowing', first.total_borrowing),
          debt_service_cost: proof('debt_service_cost', first.debt_service_cost),
        },
      };
    });
    await route.fulfill({ response, json: { ...json, history: [...json.history, ...older] } });
  });

  await page.setViewportSize({ width: 320, height: 900 });
  await page.goto('/budget');
  const history = page.getByRole('region', { name: 'The past five budgets' });
  const budget = history.getByRole('article', { name: 'Appropriated budget' });
  const callout = page.getByRole('complementary', { name: /Treasury APDMR/ });
  await expect(history.getByRole('article')).toHaveCount(4);
  await expect(callout).toContainText('KES 50.0');

  for (const width of [320, 360, 390, 400, 430, 768, 1024, 1280, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await expect(budget.getByRole('listitem')).toHaveCount(width < 400 ? 2 : 5);
    await expect(budget.getByRole('listitem').last()).toContainText('180B');
    await expect(budget.getByRole('listitem').first()).toContainText(width < 400 ? '150B' : '100B');
    await expect(budget.getByText('2019/20', { exact: true })).toHaveCount(0);
    const borrowing = history.getByRole('article', { name: 'New borrowing' });
    await expect(borrowing.getByRole('listitem')).toHaveCount(width < 400 ? 2 : 5);
    if (width >= 400) await expect(borrowing.getByRole('listitem').nth(1)).toContainText('2022/23');

    const cards = history.getByRole('article').or(callout);
    await expect.poll(() => cards.evaluateAll(elements => {
      const outside: string[] = [];
      for (const card of elements) {
        const box = card.getBoundingClientRect();
        const style = getComputedStyle(card);
        const left = box.left + parseFloat(style.borderLeftWidth) + parseFloat(style.paddingLeft);
        const right = box.right - parseFloat(style.borderRightWidth) - parseFloat(style.paddingRight);
        const check = (rect: DOMRect, label: string) => {
          if (rect.width > 0 && (rect.left < left - 1 || rect.right > right + 1)) outside.push(label);
        };
        card.querySelectorAll('*').forEach(node => {
          if (!node.closest('.sr-only')) check(node.getBoundingClientRect(), node.tagName);
        });
        const texts = document.createTreeWalker(card, NodeFilter.SHOW_TEXT);
        for (let text = texts.nextNode(); text; text = texts.nextNode()) {
          if (!text.textContent?.trim() || text.parentElement?.closest('.sr-only')) continue;
          const range = document.createRange();
          range.selectNodeContents(text);
          check(range.getBoundingClientRect(), text.textContent.trim());
        }
      }
      const callout = elements.find(card => card.tagName === 'ASIDE');
      if (callout?.parentElement) {
        const aside = callout.getBoundingClientRect();
        const header = callout.parentElement.getBoundingClientRect();
        if (aside.left < header.left - 1 || aside.right > header.right + 1) {
          outside.push('Treasury callout extends beyond its header');
        }
      }
      if (document.documentElement.scrollWidth > document.documentElement.clientWidth) outside.push('Document overflow');
      return outside;
    }), { message: `Budget content overflows at ${width}px` }).toEqual([]);

    if ([360, 768, 1440].includes(width)) {
      await testInfo.attach(`budget-history-${width}px`, { body: await history.screenshot({ style: screenshotStyle }), contentType: 'image/png' });
      await testInfo.attach(`treasury-callout-${width}px`, { body: await callout.screenshot({ style: screenshotStyle }), contentType: 'image/png' });
    }
  }

  await page.setViewportSize({ width: 360, height: 900 });
  const trigger = history.getByRole('button', { name: 'See all years' });
  expect((await trigger.boundingBox())?.height).toBeGreaterThanOrEqual(44);
  await trigger.focus();
  await page.keyboard.press('Enter');
  const sheet = page.getByRole('dialog', { name: 'Budget history' });
  await expect(sheet).toBeVisible();
  const series = sheet.getByRole('table', { name: 'Appropriated budget' });
  await expect(series.getByRole('rowheader')).toHaveText([
    '2019/20', '2020/21', '2021/22', '2022/23', '2023/24', '2024/25', '2025/26',
  ]);
  const oldest = series.getByRole('row', { name: /2019\/20/ });
  await expect(oldest).toContainText('72,000,000,000');
  await expect(oldest).toContainText('Actual');
  await expect(oldest.getByRole('link', { name: /Synthetic history report.*p\. 1/ })).toBeVisible();
  await expect(series.getByRole('row', { name: /2021\/22/ })).toContainText('100,000,000,000');
  await expect(series.getByRole('row', { name: /2022\/23/ })).toContainText('Preliminary');
  await expect(sheet.getByRole('table', { name: 'Tax + non-tax revenue' }).getByRole('row', { name: /2023\/24/ })).toContainText('Not published');
  const borrowing = sheet.getByRole('table', { name: 'New borrowing' });
  await expect(borrowing.getByRole('row', { name: /2019\/20/ })).toContainText('25,000,000,000');
  await expect(borrowing.getByRole('row', { name: /2020\/21/ })).toContainText('Withheld');
  await testInfo.attach('budget-history-sheet-360px', { body: await sheet.screenshot(), contentType: 'image/png' });
  await page.keyboard.press('Escape');
  await expect(sheet).toBeHidden();
  await expect(trigger).toBeFocused();
});
