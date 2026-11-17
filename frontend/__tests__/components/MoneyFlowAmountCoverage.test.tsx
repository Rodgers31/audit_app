import { render } from '@testing-library/react';
import MoneyFlowOverview from '@/components/transparency/MoneyFlowOverview';
import FollowTheMoney from '@/components/FollowTheMoney';
import type { AuditAmountCoverage, MoneyFlowData } from '@/types';

const coverage: AuditAmountCoverage = {
  status: 'partial', reason: 'incomplete_amount_coverage', total_findings: 3,
  findings_with_amount: 1, findings_without_amount: 1, findings_with_invalid_amount: 1,
  withheld_findings: 0,
};
const flow = (amount: number | null, c = coverage): MoneyFlowData => ({
  county_id: 501, county_name: 'Nairobi County', fiscal_year: 'FY2024/25',
  audit_amount_coverage: c, budget_source: 'cob_cbirr', total_waste_estimate: amount,
  efficiency_score: 60,
  stages: [
    { stage: 'Allocated', label: 'Budget Allocation', amount: 100 },
    { stage: 'Spent', label: 'Actual Expenditure', amount: 60, gap_from_prev: 40 },
    { stage: 'Flagged', label: 'Auditor Flagged', amount, amount_coverage: c,
      data_unavailable: amount == null },
  ],
});

function renderOverview(flagged: number | null, amountCoverage: AuditAmountCoverage) {
  render(<MoneyFlowOverview fiscalYear='2024/25' projected={false} insights={{
    allocated: 100, spent: 60, flagged, gap: 40, unspentPct: 40, efficiency: 60,
    audit_amount_coverage: amountCoverage,
  }} />);
}

it.each([0, 5.25])('shows finite audit subtotal %s with coverage in the separate overview', (flagged) => {
  renderOverview(flagged, coverage);
  expect(document.body.textContent).toContain(`KES ${flagged}`);
  expect(document.body.textContent).toContain('Partial subtotal: 1 of 3 cited findings');
  expect(document.body.textContent).toContain('1 missing and 1 invalid amounts');
  expect(document.body.textContent).not.toContain('records no questioned amount');
});

it('explains an all-invalid null without asserting the report was unpublished', () => {
  renderOverview(null, {
    ...coverage, status: 'unavailable', reason: 'invalid_stored_amount',
    total_findings: 1, findings_with_amount: 0, findings_without_amount: 0,
  });
  expect(document.body.textContent).toContain('Amount unavailable: 0 of 1 cited findings');
  expect(document.body.textContent).not.toContain('report not yet published');
});

it('shows county waterfall coverage without changing allocation or expenditure', () => {
  render(<FollowTheMoney data={flow(5.25)} isLoading={false} />);
  expect(document.body.textContent).toContain('KES 100');
  expect(document.body.textContent).toContain('KES 60');
  expect(document.body.textContent).toContain('KES 5.25');
  expect(document.body.textContent).toContain('Partial subtotal: 1 of 3 cited findings');
});
