import { quizDebtQuestion } from '@/components/learn/quizDebtQuestion';
import type { FiscalYearData } from '@/lib/api/fiscal';

const source = { url: 'https://www.treasury.go.ke/fixture.pdf', page: 24, sha256: 'a'.repeat(64) };
const fiscalYear = 'FY 2026/27';
const service = 2_315_900_000_000;
const revenue = 2_990_000_000_000;
const witness = { fiscal_year: fiscalYear, source, vintage: 'Approved', precision_kes: 1_000_000 };
const qualifications = {
  debt_service_cost: { ...witness, value_kes: service, basis: 'total_debt_service_interest_and_principal' },
  total_revenue: { ...witness, value_kes: revenue, basis: 'ordinary_revenue_excl_aia' },
};
const qualified: FiscalYearData = {
  fiscal_year: fiscalYear,
  unit: 'KES',
  total_revenue: revenue,
  debt_service_cost: service,
  debt_service_per_shilling: 77.5,
  measure_qualifications: qualifications,
  appropriated_budget: null,
  tax_revenue: null,
  non_tax_revenue: null,
  total_borrowing: null,
  borrowing_pct_of_budget: null,
  debt_ceiling: null,
  actual_debt: null,
  debt_ceiling_usage_pct: null,
  development_spending: null,
  recurrent_spending: null,
  county_allocation: null,
};

test('uses the same nearest-shilling result as the debt page, with its source and vintage', () => {
  const question = quizDebtQuestion(qualified, 'en');
  expect(question).toMatchObject({
    options: ['KES 25', 'KES 50', 'KES 78', 'KES 95'],
    correctIndex: 2,
    context: 'FY 2026/27 approved budget',
    sourceUrl: source.url,
  });
  expect(question?.explanation).toMatch(/KES 2\.32T.*KES 2\.99T/);
});

test('localizes the question and avoids duplicate choices when the live amount changes', () => {
  const amount = revenue / 2;
  const question = quizDebtQuestion({
    ...qualified,
    debt_service_cost: amount,
    debt_service_per_shilling: 50,
    measure_qualifications: { ...qualifications, debt_service_cost: { ...qualifications.debt_service_cost, value_kes: amount } },
  }, 'sw');
  expect(question?.language).toBe('sw');
  expect(question?.options).toEqual(['KES 25', 'KES 50', 'KES 95', 'KES 100']);
  expect(question?.correctIndex).toBe(1);
});

test.each<[string, Partial<FiscalYearData>]>([
  ['a missing ratio', { debt_service_per_shilling: null }],
  ['a ratio that conflicts with the source values', { debt_service_per_shilling: 78.8 }],
  ['an unlabelled unit', { unit: undefined }],
  ['an absent qualification', { measure_qualifications: {} }],
  ['a mismatched fiscal year', { fiscal_year: 'FY 2025/26' }],
  ['a mismatched amount', { total_revenue: revenue + 1 }],
  ['zero revenue', { total_revenue: 0 }],
  ['a mismatched source', { measure_qualifications: {
    ...qualifications,
    total_revenue: { ...qualifications.total_revenue, source: { ...source, sha256: 'b'.repeat(64) } },
  } }],
  ['an unsafe source link', { measure_qualifications: {
    ...qualifications,
    debt_service_cost: { ...qualifications.debt_service_cost, source: { ...source, url: 'javascript:alert(1)' } },
  } }],
  ['mixed vintages', { measure_qualifications: {
    ...qualifications,
    total_revenue: { ...qualifications.total_revenue, vintage: 'Actual' },
  } }],
])('omits the live question for %s', (_name, change) => {
  expect(quizDebtQuestion({ ...qualified, ...change }, 'en')).toBeUndefined();
});
