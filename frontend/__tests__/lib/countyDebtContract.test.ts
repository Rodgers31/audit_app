import { transformCountyData } from '@/lib/api/counties';

jest.mock('@/lib/api/axios', () => ({ apiClient: { get: jest.fn() } }));

const county = {
  id: '009', name: 'Mandera', population: null,
  budget_2025: 2000, audit_rating: '', audit_status: 'pending',
};

test('keeps source-backed debt zero and its declared coverage', () => {
  const result = transformCountyData({
    ...county, total_debt: 0, debt: 0, total_debt_absent_reason: null,
    debt_currency: 'KES', debt_accounting_basis: 'selected_instrument_outstanding',
    debt_as_at: '2025-06-30', debt_coverage: 'selected_eligible_instruments_only',
  });
  expect(result.totalDebt).toBe(0);
  expect(result.debt).toBe(0);
  expect(result.totalDebtAbsentReason).toBeNull();
  expect(result.debtCurrency).toBe('KES');
  expect(result.debtAsAt).toBe('2025-06-30');
  expect(result.debtCoverage).toBe('selected_eligible_instruments_only');
});

test('a withheld current total cannot revive an older legacy debt alias', () => {
  const result = transformCountyData({
    ...county, total_debt: null, debt: 100,
    total_debt_absent_reason: 'outstanding_not_reported_or_invalid',
  });
  expect(result.totalDebt).toBeUndefined();
  expect(result.debt).toBeUndefined();
  expect(result.totalDebtAbsentReason).toBe('outstanding_not_reported_or_invalid');
});

test.each([{ total_debt: -1, debt: 100 }, { debt: -1 }])('withholds negative debt instead of reviving another alias %p', fields => {
  const result = transformCountyData({ ...county, ...fields });
  expect(result.debt).toBeUndefined();
  expect(result.totalDebt).toBeUndefined();
});
