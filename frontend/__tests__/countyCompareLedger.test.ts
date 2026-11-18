import {
  budgetAmount, budgetComparisonBasis, comparisonRanks, debtAmount, debtComparisonBasis,
  publishedFindingCount, spentAmount, utilization, type CountySummary,
} from '@/app/counties/compare/ledgerData';

const county: CountySummary = {
  id: '001',
  name: 'Nairobi',
  budget_source: 'cob_cbirr',
  financial_summary: {
    total_allocation: 12_000_000_000,
    total_spent: 0,
    execution_rate: 0,
    fiscal_period: { label: 'FY 2024/25', start_date: '2024-07-01', end_date: '2025-06-30' },
    accounting_basis: 'reported_total',
    currency: 'KES',
    sources: [{ url: 'https://cob.go.ke/example.pdf' }],
  },
  debt: 0,
  debt_as_at: '2025-06-30',
  debt_currency: 'KES',
  debt_coverage: 'selected_eligible_instruments_only',
  debt_accounting_basis: 'selected_instrument_outstanding',
  debt_basis: 'actual',
  audit_findings_count: 0,
};

it('uses measured zero and missing fields from the financial summary', () => {
  expect(budgetAmount({ ...county, total_budget: 1 })).toBe(12_000_000_000);
  expect(utilization(county)).toBe(0);
  expect(spentAmount(county)).toBe(0);
  const absent = {
    ...county,
    total_budget: 52,
    total_spent: 52,
    budget_utilization: 0,
    financial_summary: { ...county.financial_summary, total_allocation: null, total_spent: null, execution_rate: 0 },
  };
  expect(budgetAmount(absent)).toBeNull();
  expect(spentAmount(absent)).toBeNull();
  expect(utilization(absent)).toBeNull();
  expect(utilization({ ...county, financial_summary: { ...county.financial_summary, total_allocation: 0 } })).toBeNull();
});

it('keeps older positive figures without treating projection or fallback zeros as observed', () => {
  const legacy: CountySummary = { id: '031', name: 'Laikipia', total_budget: 100, total_spent: 50, budget_utilization: 50 };
  expect([budgetAmount(legacy), spentAmount(legacy), utilization(legacy)]).toEqual([100, 50, 50]);
  const projected: CountySummary = { ...legacy, budget_source: 'cra_model', total_spent: 0, budget_utilization: 0 };
  expect([budgetAmount(projected), spentAmount(projected), utilization(projected)]).toEqual([100, null, null]);
  expect(budgetAmount({ ...legacy, total_budget: 0 })).toBeNull();
});

it('requires actual, equivalent period and source for ranking qualified budget and debt', () => {
  const budget = budgetComparisonBasis(county);
  expect(budget).toBeDefined();
  expect(budgetComparisonBasis({ ...county, budget_source: 'cra_model' })).not.toBe(budget);
  expect(budgetComparisonBasis({ ...county, financial_summary: {
    ...county.financial_summary,
    fiscal_period: { label: 'FY 2025/26', start_date: '2025-07-01', end_date: '2026-06-30' },
  } })).not.toBe(budget);
  expect(budgetComparisonBasis({ ...county, financial_summary: { ...county.financial_summary, sources: [] } })).toBeUndefined();
  expect(budgetComparisonBasis({ ...county, financial_summary: { ...county.financial_summary, sources: [{ url: 'https://cob.go.ke/another.pdf' }] } })).not.toBe(budget);
  expect(debtAmount(county)).toBe(0);
  expect(debtComparisonBasis(county)).toBe('2025-06-30');
  expect(debtComparisonBasis({ ...county, debt_basis: null })).toBeUndefined();
  expect(debtComparisonBasis({ ...county, debt_as_at: '2025-02-30' })).toBeUndefined();
  expect(debtAmount({ ...county, total_debt_absent_reason: 'unsupported_currency' })).toBeNull();
});

it('labels visible extrema only for a shared basis while keeping measured zero, ties and missing values distinct', () => {
  const entry = (amount: number | null, display = String(amount), basis = 'published-basis') => ({ amount, display, basis });
  expect(comparisonRanks([entry(0), entry(70), entry(70), entry(null)])).toEqual(['lowest', 'highest', 'highest', undefined]);
  expect(comparisonRanks([entry(0), entry(1), entry(2, '2', 'different-period')])).toEqual([undefined, undefined, undefined]);
  expect(comparisonRanks([entry(3), entry(3), entry(null)])).toEqual([undefined, undefined, undefined]);
  expect(comparisonRanks([entry(3.01, '3.0%'), entry(3.02, '3.0%')])).toEqual([undefined, undefined]);
});

it('distinguishes an empty published collection from a missing or invalid count', () => {
  expect(publishedFindingCount(county)).toBe(0);
  expect(publishedFindingCount({ ...county, audit_findings_count: 101 })).toBe(101);
  expect(publishedFindingCount({ ...county, audit_findings_count: 1.2 })).toBeNull();
  expect(publishedFindingCount({ ...county, audit_findings_count: undefined })).toBeNull();
});
