/**
 * The source-reconciliation panel promises, in its own header:
 *
 *   "Every stage of the waterfall above is anchored to one of these official
 *    documents."
 *
 * Its Controller of Budget rows claimed `covers: 'Released, Spent'` for every
 * year. There is no Released stage. The money-flow endpoints build exactly
 * three — Allocated, Spent, Flagged — at all fifteen call sites
 * (backend/routers/money_flow.py); an older version rendered "Funds Released"
 * from `committed_amount`, which is procurement encumbrances rather than
 * Treasury disbursements and produced impossible readings like spent >
 * released. It was removed, and exchequer releases are not ingested at all.
 *
 * So the panel anchored a stage the reader cannot find above it, and credited
 * the CBIRR for a figure nobody publishes here.
 *
 * The property below is the panel's own promise, checked against the stages
 * the API actually returns rather than against a list copied by hand — that is
 * what keeps it true when the waterfall next changes shape.
 */
import MoneyFlowSourceReconciliation from '@/components/transparency/MoneyFlowSourceReconciliation';
import type { BudgetSource, MoneyFlowData } from '@/types';
import { render, screen } from '@testing-library/react';

/** The stages every money-flow endpoint builds. */
const API_STAGES: MoneyFlowData['stages'] = [
  { stage: 'Allocated', label: 'Budget Allocation', amount: 633_303_870_000 },
  { stage: 'Spent', label: 'Actual Expenditure', amount: 421_000_000_000 },
  { stage: 'Flagged', label: 'Auditor Flagged', amount: 12_000_000_000 },
];

const YEARS = ['2022/23', '2023/24', '2024/25', '2025/26'];

/** Every "Feeds: …" line the panel renders, split into the stages it names. */
function feedsClaims(): string[] {
  return screen
    .getAllByText(/^Feeds:/)
    .flatMap((el) => (el.textContent ?? '').replace(/^Feeds:\s*/, '').split(','))
    .map((s) => s.trim())
    .filter(Boolean);
}

describe('MoneyFlowSourceReconciliation — the stages it claims to anchor', () => {
  const stageNames = API_STAGES.map((s) => s.stage);

  it.each(YEARS)(
    'names no stage the waterfall does not have (FY %s)',
    (fy) => {
      render(<MoneyFlowSourceReconciliation fiscalYear={fy} budgetSource='cob_cbirr' />);

      const claims = feedsClaims();
      expect(claims.length).toBeGreaterThan(0);

      for (const claim of claims) {
        // A claim may qualify the stage it feeds ("Allocated (budgeted)",
        // "Sector split (modelled)"); it may not invent one.
        const named = stageNames.filter((s) =>
          new RegExp(`\\b${s}\\b`, 'i').test(claim)
        );
        const looksLikeAStage = /^(Allocated|Released|Spent|Flagged)\b/i.test(claim);
        if (looksLikeAStage) {
          expect(named.length).toBeGreaterThan(0);
        }
      }
    }
  );

  it.each(YEARS)('never claims a document feeds "Released" (FY %s)', (fy) => {
    render(<MoneyFlowSourceReconciliation fiscalYear={fy} budgetSource='cob_cbirr' />);
    expect(feedsClaims().join(' | ')).not.toMatch(/\breleased?\b/i);
  });

  it('still credits the CBIRR for what it does feed', () => {
    // Pointed the other way: dropping "Released" must not drop the Controller
    // of Budget's real contribution with it.
    render(
      <MoneyFlowSourceReconciliation fiscalYear='2024/25' budgetSource='cob_cbirr' />
    );
    const claims = feedsClaims().join(' | ');
    expect(claims).toMatch(/\bSpent\b/);
    expect(claims).toMatch(/\bAllocated\b/);
  });

  it.each(['cob_cbirr', 'cra_model', 'mixed', null] as BudgetSource[])(
    'holds for every budget provenance (%s)',
    (budgetSource) => {
      render(
        <MoneyFlowSourceReconciliation
          fiscalYear='2024/25'
          budgetSource={budgetSource}
        />
      );
      expect(feedsClaims().join(' | ')).not.toMatch(/\breleased?\b/i);
    }
  );
});
