/**
 * The execution panel says what it measures, what it covers and where it
 * comes from (#241).
 *
 * Its footer read "Source: Controller of Budget · Quarterly Budget
 * Implementation Review" whatever it showed — a fixture, or nothing. Its rows
 * are now actual expenditure from the ANNUAL report's Section 4 sector
 * summaries, which cover ministerial spending only: Consolidated Fund
 * Services (KES 1.98T in FY 2025/26 — debt, pensions) sit outside every
 * sector. A total over ten ministerial sectors reads as the whole budget
 * unless the page says otherwise.
 */
import ExecutionAuditLens, { type ExecutionRow } from '@/components/budget/ExecutionAuditLens';
import { render, screen } from '@testing-library/react';
import React from 'react';

jest.mock('framer-motion', () => ({
  motion: new Proxy(
    {},
    {
      get:
        () =>
        ({ children, initial: _i, animate: _a, whileInView: _w, viewport: _v, transition: _t, ...props }: any) => (
          <div {...props}>{children}</div>
        ),
    }
  ),
}));

// Two rows exactly as /api/v1/budget/enhanced serves them from the FY 2025/26
// annual NG-BIRR (Table 4.1 p.94, Table 4.149 p.243).
const ROWS: ExecutionRow[] = [
  {
    sector: 'Agriculture, Rural and Urban Development',
    allocated: 117.41e9,
    spent: 103.98e9,
    unspent: 13.43e9,
    execution_rate: 88.6,
    page_ref: 'p.94',
  },
  { sector: 'Health', allocated: 164.92e9, spent: 157.2e9, unspent: 7.72e9, execution_rate: 95.3, page_ref: 'p.243' },
];

const SOURCE = {
  publisher: 'Controller of Budget',
  title: 'CoB Annual NG-BIRR FY 2025/26',
  url: 'https://cob.go.ke/download/national-government-budget-implementation-review-report-fy-2025-2026/?wpdmdl=16454',
};

it('credits the document the rows come from, with a link to it', () => {
  render(<ExecutionAuditLens rows={ROWS} fiscalYear='FY2025/26' source={SOURCE} />);
  const credit = screen.getByTestId('execution-source');
  expect(credit).toHaveTextContent('Controller of Budget · CoB Annual NG-BIRR FY 2025/26');
  expect(credit).not.toHaveTextContent('Quarterly');
  expect(credit.querySelector('a')).toHaveAttribute('href', SOURCE.url);
});

it('names the Consolidated Fund Services it leaves out', () => {
  render(
    <ExecutionAuditLens
      rows={ROWS}
      fiscalYear='FY2025/26'
      source={SOURCE}
      coverage={{ sectors_expected: 10, sectors_reported: 10, sectors_missing: [], reconciles: true }}
      excludes={{
        label: 'Consolidated Fund Services',
        description: 'public debt, pensions and constitutional office holders’ salaries',
        expenditure_bn: '1982.52',
      }}
    />
  );
  const line = screen.getByTestId('execution-coverage');
  expect(line).toHaveTextContent('Ministerial spending, 10 of 10 sectors');
  expect(line).toHaveTextContent('Excludes Consolidated Fund Services (KES 1.98T spent');
});

it('says which sectors are missing instead of drawing them at zero', () => {
  render(
    <ExecutionAuditLens
      rows={ROWS}
      fiscalYear='FY2025/26'
      coverage={{
        sectors_expected: 10,
        sectors_reported: 9,
        sectors_missing: ['National Security'],
        reconciles: true,
      }}
    />
  );
  expect(screen.getByTestId('execution-coverage')).toHaveTextContent(
    'not shown: National Security — figures did not reconcile'
  );
  expect(screen.queryByText('National Security')).toBeNull();
});

it('says so when the sectors do not add up to the report’s own total', () => {
  render(
    <ExecutionAuditLens
      rows={ROWS}
      fiscalYear='FY2024/25'
      coverage={{
        sectors_expected: 10,
        sectors_reported: 10,
        sectors_missing: [],
        sector_expenditure_bn: '2212.41',
        mda_expenditure_bn: '2215.18',
        reconciles: false,
      }}
    />
  );
  expect(screen.getByTestId('execution-coverage')).toHaveTextContent(
    "the sectors sum to KES 2212.41B against the report's ministerial total of KES 2215.18B"
  );
});
