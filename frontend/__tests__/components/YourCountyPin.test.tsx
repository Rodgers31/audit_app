import { act, render, screen } from '@testing-library/react';
import YourCountyPin from '@/app/counties/YourCountyPin';
import { readLastViewedCounty, rememberCounty } from '@/app/counties/lastViewedCounty';
import { yourCountySpendingRate } from '@/app/counties/yourCountySpendingRate';
import type { FigureQualification } from '@/lib/evidence/qualification';
import { LangProvider } from '@/lib/i18n/LangProvider';
import type { County } from '@/types';

const storageKey = 'auditgava:last-viewed-county';
const period = 'FY2024/25';

function observation(measure: string, overrides?: Partial<FigureQualification>): FigureQualification {
  return {
    status: 'qualified',
    reason: 'historical_source_not_value_checked',
    source_kind: 'pdf',
    identity: {
      measure, entity_id: 30, geography: 'Baringo County', period, unit: 'KES', basis: 'actual',
      dimensions: { category: 'Total', subcategory: null, line_type: 'total' },
    },
    source_document_id: 30,
    source_url: 'https://cob.go.ke/synthetic-budget-review.pdf',
    publisher: 'Controller of Budget',
    receipt_id: null, digest: null, locator: null, document_bytes_checked: false, value_checked: false,
    ...overrides,
  };
}

const allocation = observation('allocated_amount');
const expenditure = observation('actual_spent');
const sourcedCounty: County = {
  id: '030', name: 'Baringo', population: null, budget_2025: 10e9, budget: 10e9,
  budgetSource: 'cob_cbirr', budgetUtilization: 76, audit_rating: '', auditStatus: 'qualified',
  financial_health_score: 5,
  figureQualifications: { budget_lines: { '1': { allocated_amount: allocation, actual_spent: expenditure } } },
};

function pin(counties = [sourcedCounty], fiscalYear = period) {
  return <LangProvider><YourCountyPin counties={counties} fiscalYear={fiscalYear} spendingRate={yourCountySpendingRate} /></LangProvider>;
}

beforeEach(() => localStorage.clear());
afterEach(() => jest.restoreAllMocks());

it('stays hidden for empty or unrecognised local state and listens for a valid visit', () => {
  localStorage.setItem(storageKey, 'https://example.test/unsupported');
  render(pin());
  expect(screen.queryByRole('link', { name: /your county/i })).toBeNull();
  act(() => rememberCounty('Baringo County'));
  const link = screen.getByRole('link', { name: /your county baringo 76% spent/i });
  expect(link).toHaveAttribute('href', '/counties/baringo?fy=FY2024%2F25');
  expect(localStorage.getItem(storageKey)).toBe('baringo');
  expect(link).not.toHaveTextContent(/audit record|qualified/i);
  act(() => {
    localStorage.removeItem(storageKey);
    window.dispatchEvent(new StorageEvent('storage', { key: storageKey }));
  });
  expect(link).not.toBeInTheDocument();
});

it('uses canonical names and links with no fallback amounts when the period has no row', () => {
  rememberCounty('Murang’a County');
  expect(localStorage.getItem(storageKey)).toBe('Murang%27a');
  rememberCounty('County missing from registry');
  render(pin());
  const link = screen.getByRole('link', { name: /your county murang'a/i });
  expect(link).toHaveAttribute('href', '/counties/Murang%27a');
  expect(link).not.toHaveTextContent(/spent/i);
});

it('withholds a previously displayed value when the active year changes', () => {
  rememberCounty('Baringo');
  const { rerender } = render(pin());
  expect(screen.getByRole('link', { name: /your county.*76% spent/i })).toBeVisible();
  rerender(pin([sourcedCounty], 'FY2025/26 9M'));
  const link = screen.getByRole('link', { name: /your county baringo/i });
  expect(link).toHaveAttribute('href', '/counties/baringo?fy=FY2025%2F26%209M');
  expect(link).not.toHaveTextContent(/spent/i);
});

it('keeps the app usable if the browser denies reads or writes', () => {
  const read = jest.spyOn(Storage.prototype, 'getItem').mockImplementationOnce(() => { throw new Error('Blocked'); });
  expect(readLastViewedCounty()).toBeNull();
  read.mockRestore();
  const write = jest.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Blocked'); });
  expect(() => rememberCounty('Baringo')).not.toThrow();
  expect(write).toHaveBeenCalledTimes(1);
  expect(readLastViewedCounty()).toBeNull();
});

it('admits a published zero and withholds unconfirmed amounts and conflicting totals', () => {
  expect(yourCountySpendingRate({ ...sourcedCounty, budgetUtilization: 0 }, period)).toBe(0);
  expect(yourCountySpendingRate({ ...sourcedCounty, figureQualifications: undefined }, period)).toBeUndefined();
  expect(yourCountySpendingRate({ ...sourcedCounty, budgetSource: 'cra_model' }, period)).toBeUndefined();
  expect(yourCountySpendingRate(sourcedCounty, undefined)).toBeUndefined();

  for (const actual_spent of [
    observation('actual_spent', { status: 'conflicting' }),
    observation('actual_spent', { source_document_id: 55 }),
    observation('actual_spent', { publisher: 'Unrelated publisher' }),
    observation('actual_spent', { identity: { ...expenditure.identity, basis: 'projected' } }),
  ]) {
    const figureQualifications = { budget_lines: { '1': { allocated_amount: allocation, actual_spent } } };
    expect(yourCountySpendingRate({ ...sourcedCounty, figureQualifications }, period)).toBeUndefined();
  }

  const duplicateTotals = { '1': { allocated_amount: allocation, actual_spent: expenditure }, '2': { allocated_amount: allocation } };
  expect(yourCountySpendingRate({ ...sourcedCounty, figureQualifications: { budget_lines: duplicateTotals } }, period)).toBeUndefined();
});
