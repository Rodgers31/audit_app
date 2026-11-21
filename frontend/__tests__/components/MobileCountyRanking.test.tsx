import { render, screen, within } from '@testing-library/react';
import MobileCountyRanking, { publishedSpendingRate } from '@/app/counties/MobileCountyRanking';
import type { FigureQualification } from '@/lib/evidence/qualification';
import type { County } from '@/types';

const period = 'FY2025/26';
const officialTotal: FigureQualification = {
  status: 'qualified', reason: 'historical_source_not_value_checked', source_kind: 'pdf',
  identity: {
    measure: 'allocated_amount', entity_id: 1, geography: 'Test County', period, unit: 'KES', basis: 'actual',
    dimensions: { category: 'Total', subcategory: null, line_type: 'total' },
  },
  source_document_id: 7, source_url: 'https://cob.go.ke/synthetic-period.pdf', publisher: 'Controller of Budget',
  receipt_id: null, digest: null, locator: null, document_bytes_checked: false, value_checked: false,
};
const spending: FigureQualification = { ...officialTotal, identity: { ...officialTotal.identity, measure: 'actual_spent' } };

function testCounty(rate: number, budget = officialTotal, spent = spending): County {
  return {
    name: 'Test', id: '001', population: null, budget: 6.2e9, budget_2025: 6.2e9, audit_rating: '',
    budgetSource: 'cob_cbirr', budgetUtilization: rate,
    figureQualifications: { budget_lines: { '1': { allocated_amount: budget, actual_spent: spent } } },
  };
}

it('uses a qualified CoB Total pair with the same fiscal period and preserves a reported zero', () => {
  expect(publishedSpendingRate(testCounty(64.2), 'FY 2025/26')).toBe(64.2);
  expect(publishedSpendingRate(testCounty(0), period)).toBe(0);
  const missingBudget = { ...testCounty(0), budget: undefined };
  expect(publishedSpendingRate(missingBudget, period)).toBeUndefined();
  expect(publishedSpendingRate({ ...testCounty(0), figureQualifications: undefined }, period)).toBeUndefined();
  expect(publishedSpendingRate(testCounty(0, officialTotal, { ...spending, status: 'unavailable', reason: 'value_not_reported' }), period)).toBeUndefined();
});

it.each([
  ['conflicting', { ...spending, status: 'conflicting' }],
  ['different report', { ...spending, source_document_id: 9 }],
  ['different period', { ...spending, identity: { ...spending.identity, period: 'FY2024/25' } }],
  ['wrong basis', { ...spending, identity: { ...spending.identity, basis: 'approved' } }],
  ['invalid evidence', { ...spending, reason: 'invalid_evidence_schema' }],
  ['different publisher', { ...spending, publisher: 'Example source' }],
  ['different host', { ...spending, source_url: 'https://cob.go.ke.example.test/synthetic-period.pdf' }],
] satisfies [string, FigureQualification][])('withholds %s spending even when the legacy rate is numeric', (_case, proof) => {
  expect(publishedSpendingRate(testCounty(99, officialTotal, proof), period)).toBeUndefined();
});

it('does not use a matching historical citation when the same Total is duplicated', () => {
  const county = testCounty(90);
  county.figureQualifications!.budget_lines!['2'] = { allocated_amount: officialTotal, actual_spent: spending };
  expect(publishedSpendingRate(county, period)).toBeUndefined();
});

it('shows a supported below-target word and a period without grading other measured values', () => {
  const counties = [testCounty(69.9)];
  const formatKes = () => '6.2B';
  const { rerender } = render(<MobileCountyRanking counties={counties} paged={counties} firstRank={1} sort='utilization' fiscalYear={period} formatKes={formatKes} />);
  const list = screen.getByRole('list', { name: 'County Rankings' });
  expect(within(list).getByRole('link', { name: /Rank 1 Test 69.9%/ })).toHaveAttribute('href', '/counties/001?fy=FY2025%2F26');
  expect(within(list).getByText('Below target')).toBeInTheDocument();
  rerender(<MobileCountyRanking counties={counties} paged={counties} firstRank={1} sort='budget' fiscalYear={period} formatKes={formatKes} />);
  expect(within(list).getByText('KES 6.2B')).toBeInTheDocument();
  expect(within(list).queryByText('Below target')).not.toBeInTheDocument();
});
