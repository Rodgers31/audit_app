import { fireEvent, render, screen, within } from '@testing-library/react';
import ScoreWaterfall, { getScoreSteps } from '@/app/counties/[id]/tabs/ScoreWaterfall';
import { LangProvider } from '@/lib/i18n/LangProvider';
import type { AccountabilityScorecard, GradeFactor } from '@/types';

const factors: GradeFactor[] = [
  { impact: 'major', label: '22 audit findings (>20)', detail: 'High volume', points: -15 },
  { impact: 'moderate', label: '3 recurring query types', detail: 'Repeated across fiscal years', points: -8 },
];

type WireScorecard = Omit<Partial<AccountabilityScorecard>, 'unresolved_findings_count'> & {
  unresolved_findings_count?: number | null;
  unresolved_findings_count_reason?: string | null;
};

function scorecard(overrides: WireScorecard = {}) {
  return {
    evidence_basis: 'publishable_findings',
    accountability_grade: 'B',
    accountability_score: 77,
    grade_factors: factors,
    unresolved_findings_count: null,
    unresolved_findings_count_reason: 'resolution_status_not_published',
    ...overrides,
  } as AccountabilityScorecard;
}

it('adds the API’s ordered deductions from the published starting score', () => {
  expect(getScoreSteps(scorecard())).toMatchObject([
    { before: 100, after: 85, points: -15 },
    { before: 85, after: 77, points: -8 },
  ]);
});

it.each<WireScorecard>([
  { unresolved_findings_count: 22, unresolved_findings_count_reason: undefined },
  { evidence_basis: 'no_publishable_findings' },
  { accountability_grade: null, accountability_score: null },
  { accountability_score: 76 },
  { grade_factors: [{ ...factors[0], points: undefined }] },
  { grade_factors: [{ ...factors[0], points: 15 }] },
  { grade_factors: [{ ...factors[0], points: -101 }], accountability_grade: 'F', accountability_score: 0 },
])('returns the existing Score display when the chart inputs fail to reconcile (%j)', (overrides) => {
  expect(getScoreSteps(scorecard(overrides))).toBeNull();
});

it('accepts an explicit no-deduction factor and a reconciled score of 100', () => {
  expect(getScoreSteps(scorecard({
    accountability_score: 100,
    accountability_grade: 'A',
    grade_factors: [
      { impact: 'positive', label: 'No penalty triggers', detail: '1 published finding', points: 0 },
    ],
  }))).toEqual([]);
});

it('shows the same deduction, rule, and running score in the readout and table', () => {
  render(
    <LangProvider>
      <ScoreWaterfall county='Example' grade='B' score={77} steps={getScoreSteps(scorecard())!} />
    </LangProvider>
  );
  expect(screen.getByText('Example’s audit score: 100 minus 23 = 77, grade B.')).toBeVisible();

  const trigger = screen.getByRole('button', { name: /recurring query types|Repeat 3/ });
  const value = '−8 pt · Repeated across fiscal years · 77 left out of 100 points';
  const announcement = screen.getByText('Read chart data').parentElement!.previousElementSibling;
  expect(announcement).toHaveTextContent('Select a bar');
  fireEvent.focus(trigger);
  expect(screen.getByText(`3 recurring query types · ${value}`, { selector: '[aria-live]' })).toBeVisible();
  fireEvent.click(trigger);
  expect(trigger).toHaveAttribute('aria-pressed', 'true');
  fireEvent.keyDown(trigger, { key: 'Escape' });
  expect(trigger).toHaveAttribute('aria-pressed', 'false');
  expect(screen.queryByText(`3 recurring query types · ${value}`, { selector: '[aria-live]' })).toBeNull();

  fireEvent.click(screen.getByText('Read chart data'));
  const row = within(screen.getByRole('table', { hidden: true })).getByRole('row', {
    name: /3 recurring query types/,
    hidden: true,
  });
  expect(row).toHaveTextContent(value);
});
