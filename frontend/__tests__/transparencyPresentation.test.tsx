import TransparencyPage from '@/app/transparency/TransparencyPageClient';
import type { AuditAmountCoverage, MoneyFlowData } from '@/types';
import { fireEvent, render, screen, within } from '@testing-library/react';
import type { HTMLAttributes } from 'react';

type MockMotionProps = HTMLAttributes<HTMLElement> & {
  initial?: unknown;
  animate?: unknown;
  whileInView?: unknown;
  viewport?: unknown;
  transition?: unknown;
};

jest.mock('next/navigation', () => ({ usePathname: () => '/transparency' }));
jest.mock('framer-motion', () => ({
  motion: {
    // Keep the real page/components and remove only animation in jsdom.
    div: ({ children, initial, animate, whileInView, viewport, transition, ...props }: MockMotionProps) => (
      <div {...props}>{children}</div>
    ),
    span: ({ children, initial, animate, transition, ...props }: MockMotionProps) => (
      <span {...props}>{children}</span>
    ),
  },
  useReducedMotion: () => true,
}));
jest.mock('@/lib/react-query', () => ({
  useCountyFiscalYears: () => ({
    data: {
      years: [
        { label: 'FY2025/26 9M', source: 'cob_cbirr', counties: 3 },
        { label: 'FY2026/27', source: 'cra_model', counties: 3 },
      ],
      default: 'FY2025/26 9M',
    },
  }),
}));
jest.mock('@/lib/react-query/useMoneyFlow', () => ({
  useNationalMoneyFlow: (year: string) => ({
    data: nationalFor(year),
    isLoading: false,
  }),
  useAllCountiesMoneyFlow: (year: string) => ({
    data: countiesFor(year),
    isLoading: false,
    isError: false,
  }),
}));

// Deliberately synthetic fixtures exercise unavailable / zero / positive
// findings, the existing efficiency bands, and projection states.
function flow(
  id: number | null,
  name: string,
  allocated: number,
  spent: number | null,
  flagged: number | null,
  efficiency: number | null
): MoneyFlowData {
  return {
    county_id: id,
    county_name: name,
    fiscal_year: '2025/26 9M',
    budget_source: 'cob_cbirr',
    efficiency_score: efficiency,
    total_waste_estimate: flagged,
    audit_amount_coverage: coverageOverride,
    stages: [
      { stage: 'Allocated', label: 'Allocation', amount: allocated },
      {
        stage: 'Spent',
        label: 'Expenditure',
        amount: spent,
        gap_from_prev: spent == null ? null : allocated - spent,
      },
      { stage: 'Flagged', label: 'Questioned', amount: flagged },
    ],
  };
}
let efficiencyOverrides: number[] | undefined;
let coverageOverride: AuditAmountCoverage | undefined;

function countiesFor(year: string): MoneyFlowData[] {
  const rows = [
    flow(1, 'Alpha County', 10e9, 0, null, 0),
    flow(2, 'Beta County', 20e9, 12e9, 0, 60),
    flow(3, 'Gamma County', 30e9, 24e9, 2e9, 80),
  ];
  if (year === '2026/27')
    return rows.map((row) => ({
      ...row,
      fiscal_year: year,
      budget_source: 'cra_model',
      efficiency_score: null,
      stages: row.stages.map((stage) =>
        stage.stage === 'Allocated' ? stage : { ...stage, amount: null, gap_from_prev: null }
      ),
    }));
  return rows.map((row, index) => ({
    ...row,
    efficiency_score: efficiencyOverrides?.[index] ?? row.efficiency_score,
  }));
}
function nationalFor(year: string): MoneyFlowData {
  return year === '2026/27'
    ? {
        ...flow(null, 'National', 60e9, null, null, null),
        fiscal_year: year,
        budget_source: 'cra_model',
      }
    : flow(null, 'National', 60e9, 36e9, 2e9, efficiencyOverrides?.[1] ?? 60);
}
const countyList = () => screen.getByRole('list', { name: /Counties ordered by/ });
const county = (name: string) => screen.getByRole('link', { name }).closest('li')!;
const overview = () => screen.getByRole('region', { name: 'At a glance' });

describe('Follow the Money presentation contracts', () => {
  beforeEach(() => {
    efficiencyOverrides = undefined;
    coverageOverride = undefined;
    jest.useFakeTimers();
    jest.setSystemTime(new Date('2026-09-27T12:00:00Z'));
  });
  afterEach(() => jest.useRealTimers());

  it('preserves source amounts, zero spending, and the difference between unavailable and zero findings', () => {
    render(<TransparencyPage />);
    expect(within(county('Alpha')).getByLabelText('Flagged amount unavailable')).toHaveTextContent(
      '—'
    );
    expect(county('Alpha')).toHaveTextContent('KES 0');
    expect(county('Alpha')).toHaveTextContent('Low execution');
    expect(county('Beta')).toHaveTextContent('FlaggedKES 0');
    expect(county('Beta')).toHaveTextContent('Fair execution');
    expect(county('Gamma')).toHaveTextContent('FlaggedKES 2.00B');
    expect(county('Gamma')).toHaveTextContent('Amounts discussed; not proven loss');
    expect(county('Gamma')).toHaveTextContent('Good execution');
    expect(screen.getByRole('link', { name: 'Gamma' })).toHaveAttribute(
      'href',
      '/counties/3?tab=money&from=transparency'
    );
    expect(overview()).toHaveTextContent('KES 24.00B');
    expect(overview()).toHaveTextContent('40.0% of allocation unspent');
  });

  it('carries partial coverage through the actual page into county rows and the national summary', () => {
    coverageOverride = {
      status: 'partial', reason: 'incomplete_amount_coverage', total_findings: 3,
      findings_with_amount: 1, findings_without_amount: 1, findings_with_invalid_amount: 1,
      withheld_findings: 0,
    };
    render(<TransparencyPage />);
    expect(county('Beta')).toHaveTextContent('FlaggedKES 0');
    expect(county('Beta')).toHaveTextContent('Partial subtotal: 1 of 3 cited findings');
    expect(county('Gamma')).toHaveTextContent('FlaggedKES 2.00B');
    expect(county('Gamma')).toHaveTextContent('1 missing and 1 invalid amounts');
    expect(overview()).toHaveTextContent('Partial subtotal: 1 of 3 cited findings');
  });

  it('searches and reverses all sort modes while preserving the national summary and coverage', () => {
    render(<TransparencyPage />);
    const originalSummary = overview().textContent;
    fireEvent.change(screen.getByLabelText('Sort by'), {
      target: { value: 'flagged' },
    });
    expect(within(countyList()).getAllByRole('link')[0]).toHaveTextContent('Gamma');
    fireEvent.change(screen.getByLabelText('Sort by'), {
      target: { value: 'gap' },
    });
    expect(within(countyList()).getAllByRole('link')[0]).toHaveTextContent('Alpha');
    fireEvent.change(screen.getByLabelText('Sort by'), {
      target: { value: 'name' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Reverse sort order' }));
    expect(within(countyList()).getAllByRole('link')[0]).toHaveTextContent('Gamma');
    fireEvent.change(screen.getByLabelText('Find your county'), {
      target: { value: ' Beta ' },
    });
    expect(within(countyList()).getAllByRole('listitem')).toHaveLength(1);
    expect(overview().textContent).toBe(originalSummary);
    expect(screen.getByText(/3 of 47 counties have published allocations/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Find your county'), {
      target: { value: 'Missing' },
    });
    expect(screen.getByText('No counties match your search.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Clear search' }));
    expect(within(countyList()).getAllByRole('listitem')).toHaveLength(3);
  });

  it('changes reporting period without losing projection shares or treating a filtered empty list as execution data', () => {
    render(<TransparencyPage />);
    fireEvent.change(screen.getByLabelText('Fiscal year & reporting period'), {
      target: { value: '2026/27' },
    });
    expect(overview()).toHaveTextContent('Spent so far');
    expect(overview()).toHaveTextContent('Not yet audited');
    expect(county('Alpha')).toHaveTextContent('16.7% of national allocation');
    fireEvent.change(screen.getByLabelText('Find your county'), {
      target: { value: 'Alpha' },
    });
    expect(county('Alpha')).toHaveTextContent('16.7% of national allocation');
    fireEvent.change(screen.getByLabelText('Find your county'), {
      target: { value: 'Missing' },
    });
    expect(overview()).toHaveTextContent('Spent so far');
    expect(overview()).toHaveTextContent('Not yet audited');
    expect(screen.getByLabelText('Sort by')).toHaveValue('allocated');
  });

  it('keeps the selected sort and actual order aligned after switching back from a projection', () => {
    render(<TransparencyPage />);
    fireEvent.change(screen.getByLabelText('Fiscal year & reporting period'), {
      target: { value: '2026/27' },
    });
    fireEvent.change(screen.getByLabelText('Sort by'), { target: { value: 'name' } });
    fireEvent.change(screen.getByLabelText('Sort by'), { target: { value: 'allocated' } });
    fireEvent.change(screen.getByLabelText('Fiscal year & reporting period'), {
      target: { value: '2025/26 9M' },
    });
    expect(screen.getByLabelText('Sort by')).toHaveValue('efficiency');
    expect(
      within(countyList())
        .getAllByRole('link')
        .map((link) => link.textContent)
    ).toEqual(['Alpha', 'Beta', 'Gamma']);
  });

  it('does not round percentages across the execution bands shown in the legend', () => {
    efficiencyOverrides = [49.99, 69.99, 70];
    render(<TransparencyPage />);
    expect(county('Alpha')).toHaveTextContent('49.99%Low execution');
    expect(county('Beta')).toHaveTextContent('69.99%Fair execution');
    expect(county('Gamma')).toHaveTextContent('70%Good execution');
    expect(overview()).toHaveTextContent('69.99%');
  });
});
