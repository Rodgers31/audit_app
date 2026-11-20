import { render, screen } from '@testing-library/react';
import CountyDevelopmentMeter from '@/app/counties/[id]/tabs/CountyDevelopmentMeter';
import { countyDevelopmentShare } from '@/app/counties/[id]/tabs/developmentShare';
import type { FigureQualification } from '@/lib/evidence/qualification';

const document = { id: 9, title: 'Synthetic county budget report', publisher: 'Controller of Budget',
  url: 'https://example.test/county-budget.pdf' };
const period = { label: 'FY2025/26', start_date: '2025-07-01T00:00:00', end_date: '2026-06-30T00:00:00' };
function row(category: string, patch: Partial<FigureQualification> = {}) {
  return { allocated_amount: {
    status: 'qualified', reason: 'historical_source_not_value_checked', source_kind: 'unknown',
    identity: { measure: 'allocated_amount', entity_id: 33, geography: 'Baringo County',
      period: period.label, unit: 'KES', basis: 'actual', dimensions: { category, subcategory: null } },
    source_document_id: document.id, source_url: document.url, publisher: document.publisher,
    receipt_id: null, digest: null, locator: null, document_bytes_checked: false, value_checked: false,
    ...patch,
  } satisfies FigureQualification };
}
const records = { '11': row('Total'), '12': row('Development'), '13': row('Recurrent') };
const budget = { fiscal_year: period.label, fiscal_period: period, source: null,
  accounting_basis: 'reported_total', sources: [document], figure_qualifications: records,
  total_allocated: 10_075_960_000, development_budget: 4_186_860_000, recurrent_budget: 5_889_100_000,
  total_spent: 7_665_520_000, utilization_rate: 76.077, per_capita_budget: null, sector_breakdown: {},
};

it('uses the same sourced allocation and exact report period beside the medium-term benchmark', () => {
  const share = countyDevelopmentShare(budget, 'Baringo');
  expect(share).toMatchObject({ projects: 4_186_860_000, total: 10_075_960_000, sourceLinkedOnly: true });
  render(<CountyDevelopmentMeter share={share} />);
  expect(screen.getByRole('meter')).toHaveAttribute('aria-valuetext', '41.6% for development');
  expect(screen.getByText('30% medium-term benchmark')).toBeVisible();
  expect(screen.getByText(/FY2025\/26.*1 July 2025 to 30 June 2026/, { selector: 'section > p' })).toBeVisible();
  expect(screen.getByText(/over three to five years/, { selector: 'section > p' })).toBeVisible();
  expect(screen.queryByText(/On track|compliant/i)).toBeNull();
});

it('admits a published zero and withholds a zero filled from missing data', () => {
  const zero = { ...budget, development_budget: 0, recurrent_budget: budget.total_allocated };
  const measured = countyDevelopmentShare(zero, 'Baringo');
  expect(measured?.rate).toBe(0);
  const { rerender } = render(<CountyDevelopmentMeter share={measured} />);
  expect(screen.getByRole('meter')).toHaveAttribute('aria-valuenow', '0');
  const missing = countyDevelopmentShare({ ...zero, figure_qualifications: {
    ...records, '12': row('Development', { status: 'unavailable', reason: 'value_not_reported' }),
  } }, 'Baringo');
  expect(missing).toBeNull();
  rerender(<CountyDevelopmentMeter share={missing} />);
  expect(screen.getByText('Development share unavailable for this budget.')).toBeVisible();
  expect(screen.queryByRole('meter')).toBeNull();
});

it('allows the backend’s explicitly reconciled two-component accounting basis', () => {
  const { 12: development, 13: recurrent } = records;
  const classified = { ...budget, accounting_basis: 'recurrent_plus_development',
    figure_qualifications: { '12': development, '13': recurrent } };
  expect(countyDevelopmentShare(classified, 'Baringo')?.rate).toBeCloseTo(41.55, 1);
  expect(countyDevelopmentShare({ ...classified, figure_qualifications: records }, 'Baringo')).toBeNull();
});

it('rejects a duplicate, mismatched, unverified or irreconcilable split before publishing a share', () => {
  const identity = records['12'].allocated_amount.identity;
  for (const fix of [
    { identity: { ...identity, period: 'FY2024/25' } },
    { identity: { ...identity, entity_id: 34 } },
    { identity: { ...identity, geography: 'Nandi County' } },
    { identity: { ...identity, unit: 'USD' } },
    { identity: { ...identity, basis: 'projected' } },
    { source_document_id: 10 },
    { source_url: 'https://example.test/different.pdf' },
    { status: 'conflicting', reason: 'observation_identity_mismatch' },
    { status: 'verified', document_bytes_checked: true, value_checked: false },
  ] satisfies Partial<FigureQualification>[]) {
    expect(countyDevelopmentShare({ ...budget, figure_qualifications: { ...records, '12': row('Development', fix) } }, 'Baringo')).toBeNull();
  }
  const duplicate = { ...records, '14': row('Development', { source_document_id: 10 }) };
  expect(countyDevelopmentShare({ ...budget, figure_qualifications: duplicate }, 'Baringo')).toBeNull();
  expect(countyDevelopmentShare({ ...budget, recurrent_budget: budget.recurrent_budget + 1000 }, 'Baringo')).toBeNull();
  expect(countyDevelopmentShare({ ...budget, source: 'cra_model' }, 'Baringo')).toBeNull();
  expect(countyDevelopmentShare({ ...budget, fiscal_year: 'FY2024/25' }, 'Baringo')).toBeNull();
});
