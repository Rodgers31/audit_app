import TransparencyPage from '@/app/transparency/TransparencyPageClient';
import MoneyFlowHero from '@/components/transparency/MoneyFlowHero';
import { isProjectedMoneyFlow } from '@/components/transparency/moneyFlowPresentation';
import type { BudgetSource, MoneyFlowData } from '@/types';
import { fireEvent, render, screen, within } from '@testing-library/react';
import type { HTMLAttributes } from 'react';

type MotionProps = HTMLAttributes<HTMLElement> & {
  initial?: unknown;
  animate?: unknown;
  whileInView?: unknown;
  viewport?: unknown;
  transition?: unknown;
};

jest.mock('next/navigation', () => ({ usePathname: () => '/transparency' }));
jest.mock('framer-motion', () => ({
  motion: {
    div: ({
      children,
      initial,
      animate,
      whileInView,
      viewport,
      transition,
      ...props
    }: MotionProps) => <div {...props}>{children}</div>,
    span: ({ children, initial, animate, transition, ...props }: MotionProps) => (
      <span {...props}>{children}</span>
    ),
  },
  useReducedMotion: () => true,
}));
jest.mock('@/lib/react-query', () => ({
  useCountyFiscalYears: () => ({
    data: {
      years: [{ label: `FY${mockYear}`, source: 'cra_model', counties: 47 }],
      default: `FY${mockYear}`,
    },
  }),
}));
jest.mock('@/lib/react-query/useMoneyFlow', () => ({
  useNationalMoneyFlow: () => ({ data: mockNational, isLoading: false }),
  useAllCountiesMoneyFlow: () => ({
    data: mockCounties,
    isLoading: mockCountiesLoading,
    isError: false,
  }),
}));

// Synthetic response shapes, not national/county figures for publication.
function flow({
  countyId = null,
  name = 'National (All Counties)',
  allocated = 100e9,
  spent = null,
  flagged = null,
  efficiency = null,
  budgetSource = 'cra_model',
  year = '2026/27',
}: {
  countyId?: number | null;
  name?: string;
  allocated?: number | null;
  spent?: number | null;
  flagged?: number | null;
  efficiency?: number | null;
  budgetSource?: BudgetSource;
  year?: string;
} = {}): MoneyFlowData {
  return {
    county_id: countyId,
    county_name: name,
    fiscal_year: year,
    budget_source: budgetSource,
    efficiency_score: efficiency,
    total_waste_estimate: flagged,
    stages: [
      { stage: 'Allocated', label: 'Allocation', amount: allocated },
      {
        stage: 'Spent',
        label: 'Expenditure',
        amount: spent,
        gap_from_prev: allocated == null || spent == null ? null : allocated - spent,
      },
      { stage: 'Flagged', label: 'Questioned', amount: flagged },
    ],
  };
}

let mockYear: string;
let mockNational: MoneyFlowData;
let mockCounties: MoneyFlowData[] | undefined;
let mockCountiesLoading: boolean;

const county = (name: string) => screen.getByRole('link', { name }).closest('li')!;
const overview = () => screen.getByRole('region', { name: 'At a glance' });

function sourceSection() {
  return screen.getByRole('heading', { name: 'Source reconciliation' }).closest('section')!;
}

describe('Review regression: national summary and source states', () => {
  beforeEach(() => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date('2026-09-28T12:00:00Z'));
    mockYear = '2026/27';
    mockNational = flow();
    mockCounties = [
      flow({ countyId: 1, name: 'Alpha County', allocated: 20e9 }),
      flow({ countyId: 2, name: 'Beta County', allocated: null }),
    ];
    mockCountiesLoading = false;
  });
  afterEach(() => jest.useRealTimers());

  it('uses the complete national response rather than the partial county allocation pool', () => {
    render(<TransparencyPage />);
    expect(county('Alpha')).toHaveTextContent('20.0% of national allocation');
    expect(county('Beta')).toHaveTextContent('— of national allocation');
    fireEvent.change(screen.getByLabelText('Find your county'), { target: { value: 'Alpha' } });
    expect(county('Alpha')).toHaveTextContent('20.0% of national allocation');
  });

  it.each([null, 0])(
    'does not invent a national share when national allocation is %s',
    (allocated) => {
      mockNational = flow({ allocated });
      render(<TransparencyPage />);
      expect(county('Alpha')).not.toHaveTextContent(/\d+(?:\.\d+)?% of national allocation/);
    }
  );

  it('keeps the national pending-execution summary stable when the national response arrives first', () => {
    mockCounties = undefined;
    mockCountiesLoading = true;
    const view = render(<TransparencyPage />);
    expect(overview()).toHaveTextContent('Spent so far');
    const pendingSummary = overview().textContent;
    mockCountiesLoading = false;
    mockCounties = [flow({ countyId: 1, name: 'Alpha County', allocated: 20e9 })];
    view.rerender(<TransparencyPage />);
    expect(overview().textContent).toBe(pendingSummary);
  });

  it.each([null, 0])(
    'retains independently available audit and efficiency values with allocation %s',
    (allocated) => {
      mockYear = '2023/24';
      mockNational = flow({
        allocated,
        spent: 40e9,
        flagged: 3e9,
        efficiency: 40,
        year: mockYear,
        budgetSource: 'cob_cbirr',
      });
      mockCounties = [];
      render(<TransparencyPage />);
      expect(overview()).toHaveTextContent('KES 3.00B');
      expect(overview()).toHaveTextContent('40%');
      expect(overview()).not.toHaveTextContent('Not yet audited');
    }
  );

  it('does not mistake a closed CBIRR period with missing expenditure for a current CRA projection', () => {
    render(<MoneyFlowHero data={flow({ year: '2023/24', budgetSource: 'cob_cbirr' })} />);
    expect(screen.getByText('Controller of Budget CBIRR county aggregates')).toBeInTheDocument();
    expect(screen.queryByText(/CRA Budget Estimate/)).not.toBeInTheDocument();
    expect(screen.queryByText(/This fiscal year is still being executed/)).not.toBeInTheDocument();
  });

  it('does not attribute CRA allocations to Controller of Budget when expenditure is available', () => {
    const { container } = render(
      <MoneyFlowHero data={flow({ spent: 50e9, budgetSource: 'cra_model' })} />
    );
    const sourceLabel = container.querySelector('header > p');
    expect(sourceLabel).toHaveTextContent(/CRA/);
    expect(sourceLabel).not.toHaveTextContent(/^Controller of Budget \+ OAG/);
    expect(screen.getByText('CRA equitable-share model — not CoB-reported')).toBeInTheDocument();
  });

  it('does not replace published audit or efficiency figures with projection placeholders', () => {
    mockNational = flow({ flagged: 2e9, efficiency: 45 });
    render(<TransparencyPage />);
    expect(overview()).toHaveTextContent('KES 2.00B');
    expect(overview()).toHaveTextContent('45%');
    expect(within(overview()).queryByText('Not yet audited')).not.toBeInTheDocument();
  });

  it('links the actual CBIRR report for a subperiod without inventing CRA allocation provenance', () => {
    mockYear = '2025/26 9M';
    mockNational = {
      ...flow({ year: mockYear, budgetSource: 'cob_cbirr', spent: 50e9 }),
      source_document_title: 'Synthetic CBIRR nine-month report',
      source_document_url: 'https://cob.go.ke/reports/synthetic-cbirr-nine-month.pdf',
    };
    render(<TransparencyPage />);
    const sources = sourceSection();
    expect(
      within(sources)
        .getAllByRole('link')
        .some((link) => link.getAttribute('href') === mockNational.source_document_url)
    ).toBe(true);
    const cra = within(sources).queryByText('Commission on Revenue Allocation');
    if (cra) expect(cra.closest('li')).not.toHaveTextContent('Feeds: Allocated');
  });

  it('keeps a stage-level source document when the national source URL is absent', () => {
    mockYear = '2025/26 9M';
    mockNational = flow({ year: mockYear, budgetSource: 'cob_cbirr', spent: 50e9 });
    mockNational.stages[0].source_doc = 'https://cob.go.ke/reports/synthetic-allocation.pdf';
    render(<TransparencyPage />);
    expect(
      within(sourceSection())
        .getAllByRole('link')
        .some((link) => link.getAttribute('href') === mockNational.stages[0].source_doc)
    ).toBe(true);
  });

  it.each([
    { spent: 0, flagged: null, efficiency: 0, visible: '0%Low execution' },
    { spent: null, flagged: 2e9, efficiency: null, visible: 'FlaggedKES 2.00B' },
    { spent: null, flagged: null, efficiency: 45, visible: '45%Low execution' },
  ])(
    'preserves county evidence independently of a still-projected national response ($visible)',
    ({ spent, flagged, efficiency, visible }) => {
      mockCounties = [
        flow({
          countyId: 1,
          name: 'Alpha County',
          allocated: 20e9,
          spent,
          flagged,
          efficiency,
          budgetSource: 'cob_cbirr',
        }),
        flow({ countyId: 2, name: 'Beta County', allocated: 10e9 }),
      ];
      render(<TransparencyPage />);
      expect(overview()).toHaveTextContent('Spent so far');
      expect(county('Alpha')).toHaveTextContent(visible);
      expect(county('Alpha')).not.toHaveTextContent('Execution pending');
      expect(screen.getByLabelText('Sort by')).toHaveValue('efficiency');
      fireEvent.change(screen.getByLabelText('Find your county'), { target: { value: 'Beta' } });
      expect(screen.getByLabelText('Sort by')).toHaveValue('efficiency');
      expect(overview()).toHaveTextContent('Spent so far');
    }
  );

  it('does not promise publication from a fiscal-year label when no report is linked', () => {
    mockYear = '2023/24';
    mockNational = flow({ allocated: null, budgetSource: null, year: mockYear });
    mockCounties = [];
    render(<TransparencyPage />);
    expect(within(sourceSection()).queryAllByText('Published')).toHaveLength(0);
    expect(sourceSection()).not.toHaveTextContent('Every stage of the waterfall above is anchored');
  });
});

describe('Review verification: projection and source boundaries', () => {
  it.each([
    ['absent response', undefined, false],
    ['null response', null, false],
    ['CRA allocation only', flow(), true],
    ['published zero allocation', flow({ allocated: 0 }), true],
    ['allocation unavailable', flow({ allocated: null }), false],
    ['CoB allocation only', flow({ budgetSource: 'cob_cbirr' }), false],
    ['mixed allocation only', flow({ budgetSource: 'mixed' }), false],
    ['unknown allocation source', flow({ budgetSource: null }), false],
    ['published zero spend', flow({ spent: 0 }), false],
    ['published zero questioned', flow({ flagged: 0 }), false],
    ['published zero efficiency', flow({ efficiency: 0 }), false],
    ['no stages', { ...flow(), stages: [] }, false],
    ['only allocated stage', { ...flow(), stages: [flow().stages[0]] }, true],
    ['only audit stage', { ...flow(), stages: [flow({ flagged: 2e9 }).stages[2]] }, false],
  ] as [string, MoneyFlowData | null | undefined, boolean][])(
    '%s preserves the projection contract',
    (_label, data, expected) => {
      expect(isProjectedMoneyFlow(data)).toBe(expected);
    }
  );

  it.each([
    'javascript:alert(1)',
    'data:text/html,bad',
    'file:///tmp/report.pdf',
    '//cob.go.ke/report.pdf',
    'not a URL',
  ])('does not turn unsafe or malformed source URL %s into a report link', (sourceURL) => {
    mockYear = '2025/26 9M';
    mockNational = {
      ...flow({ year: mockYear, budgetSource: 'cob_cbirr', spent: 50e9 }),
      source_document_url: sourceURL,
    };
    mockNational.stages = mockNational.stages.map((stage) => ({ ...stage, source_doc: sourceURL }));
    mockCounties = [];
    mockCountiesLoading = false;
    render(<TransparencyPage />);
    const sources = sourceSection();
    expect(
      within(sources).queryByRole('link', { name: 'View source document' })
    ).not.toBeInTheDocument();
    for (const link of within(sources).getAllByRole('link'))
      expect(link.getAttribute('href')).toMatch(/^https:\/\//);
  });

  it.each(['cob_cbirr', 'cra_model', 'mixed', null] as const)(
    'does not lend a national CoB source URL to the auditor or a CRA allocation (%s)',
    (budgetSource) => {
      const cobURL = 'https://cob.go.ke/reports/synthetic-national.pdf';
      mockYear = '2025/26 9M';
      mockNational = { ...flow({ year: mockYear, budgetSource }), source_document_url: cobURL };
      mockCounties = [];
      mockCountiesLoading = false;
      render(<TransparencyPage />);
      const rows = within(sourceSection()).getAllByRole('listitem');
      const [allocation, spending, audit] = rows;
      expect(within(spending).getByRole('link')).toHaveAttribute('href', cobURL);
      expect(within(audit).getByRole('link')).not.toHaveAttribute('href', cobURL);
      if (budgetSource !== 'cob_cbirr') {
        expect(
          within(allocation).queryByRole('link', { name: 'View source document' })
        ).not.toBeInTheDocument();
      }
    }
  );

  it('uses the flagged stage report instead of borrowing the national budget document', () => {
    const auditURL = 'https://oagkenya.go.ke/reports/synthetic-audit.pdf';
    mockYear = '2023/24';
    mockNational = {
      ...flow({ year: mockYear, budgetSource: 'cob_cbirr', flagged: 3e9 }),
      source_document_url: 'https://cob.go.ke/reports/synthetic-national.pdf',
    };
    mockNational.stages[2].source_doc = auditURL;
    mockCounties = [];
    mockCountiesLoading = false;
    render(<TransparencyPage />);
    const audit = within(sourceSection()).getAllByRole('listitem')[2];
    expect(within(audit).getByRole('link')).toHaveAttribute('href', auditURL);
  });
});
