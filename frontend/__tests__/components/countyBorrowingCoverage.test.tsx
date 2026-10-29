import { render, screen } from '@testing-library/react';
import ModelledDataNote from '@/components/ModelledDataNote';
import { LangProvider } from '@/lib/i18n/LangProvider';

test('county source note describes application coverage without claiming counties have no debt', () => {
  render(<LangProvider><ModelledDataNote /></LangProvider>);
  expect(screen.getByRole('note')).toHaveTextContent('does not mean zero debt');
  expect(screen.getByRole('note')).not.toHaveTextContent('most counties have none');
});

import CountyBorrowingNote from '@/components/county/CountyBorrowingNote';
import { borrowingCoverageKey, borrowingSources, type BorrowingCoverage } from '@/lib/countyBorrowingCoverage';

test.each([
  [null, 'no_eligible_instruments', undefined, undefined, 'not_integrated'],
  [null, 'duplicate_instrument_observations', undefined, undefined, 'withheld'],
  [Infinity, null, undefined, undefined, 'withheld'],
  [-1, null, undefined, undefined, 'withheld'],
  [0, null, undefined, '2025-06-30', 'zero'],
  [0, null, undefined, undefined, 'selected'],
  [100, null, undefined, '2025-06-30', 'selected'],
  [null, null, { status: 'not_reported_in_checked_source', sources: [] }, undefined, 'not_integrated'],
] as const)('classifies the actual value and evidence: %s', (balance, reason, coverage, date, expected) => {
  expect(borrowingCoverageKey(balance, reason, coverage, date)).toBe(`county.borrowing.${expected}`);
});

test('checked-source absence keeps scope and accessible provenance separate from zero', () => {
  render(<LangProvider><CountyBorrowingNote balance={null} coverage={{
    status: 'not_reported_in_checked_source', complete_liability_coverage: false,
    sources: [{url: 'https://www.treasury.go.ke/report.pdf', scope: 'guarantees_only', pdf_pages: [53]}],
  }} /></LangProvider>);
  expect(screen.getByRole('note')).toHaveTextContent('checked source scope');
  expect(screen.getByRole('note')).toHaveTextContent('Other borrowing and liabilities may exist');
  expect(screen.getByRole('link', {name: /Checked source 1/})).toHaveAttribute('href', 'https://www.treasury.go.ke/report.pdf');
});


test('conflicting evidence and invalid stock dates cannot certify a balance', () => {
  expect(borrowingCoverageKey(20, 'duplicate_instrument_observations')).toBe('county.borrowing.withheld');
  expect(borrowingCoverageKey(0, null, undefined, '2025-99-99')).toBe('county.borrowing.selected');
});

test.each(['malformed', [{url: 'https://example.invalid', scope: 'test', pdf_pages: null}], [null]])(
  'malformed coverage cannot crash or claim checked sources: %p', sources => {
    const coverage = {status: 'not_reported_in_checked_source', sources} as unknown as BorrowingCoverage;
    render(<LangProvider><CountyBorrowingNote balance={null} coverage={coverage} /></LangProvider>);
    expect(screen.getByRole('note')).toHaveTextContent('does not mean zero debt');
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  },
);

import CountyDetailsPanel from '@/components/dashboard/CountyDetailsPanel';
import type { County } from '@/types';

test('home county panel keeps a reported zero balance visible', () => {
  const county = { id: 'code:045', name: 'Kisii', debt: 0, totalDebt: 0, debtAsAt: '2025-06-30',
    auditStatus: 'pending', population: null } as County;
  render(<LangProvider><CountyDetailsPanel county={county} /></LangProvider>);
  expect(screen.getByText('KES 0')).toBeInTheDocument();
  expect(screen.getAllByRole('note').map(node => node.textContent).join(' ')).toContain('dated zero');
});

test('checked source dates distinguish the reporting period from the scope review', () => {
  render(<LangProvider><CountyBorrowingNote balance={null} coverage={{
    status: 'not_reported_in_checked_source', complete_liability_coverage: false,
    sources: [{url: 'https://www.treasury.go.ke/report.pdf', scope: 'guarantees_only', pdf_pages: [53],
      reporting_period_end: '2025-06-30', scope_reviewed_on: '2026-10-25'}],
  }} /></LangProvider>);
  expect(screen.getByRole('note')).toHaveTextContent('Report period ended: 2025-06-30');
  expect(screen.getByRole('note')).toHaveTextContent('Source scope reviewed: 2026-10-25');
  expect(screen.getByRole('note')).not.toHaveTextContent('Published');
  expect(screen.getByRole('note')).not.toHaveTextContent('dated zero');
});

test('unknown scope review date is not completed from the reporting date', () => {
  render(<LangProvider><CountyBorrowingNote balance={null} coverage={{
    status: 'withheld_or_conflicting', complete_liability_coverage: false,
    sources: [{url: 'https://www.oagkenya.go.ke/report.pdf', scope: 'audit_finding', pdf_pages: [499],
      reporting_period_end: '2024-06-30', scope_reviewed_on: null}],
  }} /></LangProvider>);
  expect(screen.getByRole('note')).toHaveTextContent('Report period ended: 2024-06-30');
  expect(screen.getByRole('note')).not.toHaveTextContent('Source scope reviewed:');
});

test.each(['2026-02-30', '2026-10', '2026-10-25T00:00:00Z', true, 20261025])(
  'malformed scope review date cannot be rendered as source authority: %p', scope_reviewed_on => {
    const coverage = {status: 'not_reported_in_checked_source', sources: [{
      url: 'https://www.treasury.go.ke/report.pdf', scope: 'guarantees_only', pdf_pages: [53],
      reporting_period_end: '2025-06-30', scope_reviewed_on,
    }]} as unknown as BorrowingCoverage;
    render(<LangProvider><CountyBorrowingNote balance={null} coverage={coverage} /></LangProvider>);
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    expect(screen.getByRole('note')).not.toHaveTextContent('Source scope reviewed:');
  },
);

test.each(['2026-10-29', '2999-01-01'])(
  'a future scope review cannot authorize a source citation: %s', scope_reviewed_on => {
    jest.useFakeTimers().setSystemTime(new Date('2026-10-28T23:59:59.000Z'));
    try {
      const coverage: BorrowingCoverage = {status: 'not_reported_in_checked_source', sources: [{
        url: 'https://www.treasury.go.ke/report.pdf', scope: 'guarantees_only', pdf_pages: [53],
        reporting_period_end: '2025-06-30', scope_reviewed_on,
      }]};
      expect(borrowingSources(coverage)).toEqual([]);
      render(<LangProvider><CountyBorrowingNote balance={null} coverage={coverage} /></LangProvider>);
      expect(screen.queryByRole('link')).not.toBeInTheDocument();
      expect(screen.getByRole('note')).not.toHaveTextContent('Source scope reviewed:');
    } finally {
      jest.useRealTimers();
    }
  },
);

test('scope review uses the current UTC day and keeps legacy undated citations', () => {
  jest.useFakeTimers().setSystemTime(new Date('2026-10-28T00:00:00.000Z'));
  try {
    const source = {url: 'https://www.treasury.go.ke/report.pdf', scope: 'guarantees_only', pdf_pages: [53]};
    expect(borrowingSources({sources: [source]})).toHaveLength(1);
    expect(borrowingSources({sources: [{...source, scope_reviewed_on: '2026-10-28'}]})).toHaveLength(1);
    expect(borrowingSources({sources: [{...source, scope_reviewed_on: '2026-10-29'}]})).toEqual([]);
  } finally {
    jest.useRealTimers();
  }
});
