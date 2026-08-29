import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';

// The exact shape /api/v1/audits/federal returns when the publication gate
// withholds every federal finding (verified against the live DB 2026-08-29:
// 26 ministry/national rows withheld, 0 published).
const GATED_EMPTY_RESPONSE = {
  report_title: null,
  auditor_general: 'Office of the Auditor General of Kenya',
  fiscal_year: null,
  report_date: null,
  opinion_type: null,
  total_findings: 0,
  total_amount_questioned: null,
  total_amount_questioned_label: null,
  withheld_findings: 26,
  by_severity: {},
  findings_reason: 'awaiting_sourced_data',
  next_expected: {
    dataset: 'oag_national_audits',
    publisher: 'Office of the Auditor-General',
    cadence: 'annual',
    lag: '6-9',
    lag_unit: 'months',
    window_start: '2026-12-01',
    window_end: '2027-04-30',
    in_window: false,
  },
  basis_for_qualification: [],
  emphasis_of_matter: [],
  key_statistics: {},
  findings: [],
  top_ministries: [],
  last_updated: null,
};

const mockUseFederalAudits = jest.fn();
jest.mock('@/lib/react-query/useAudits', () => ({
  useFederalAudits: () => mockUseFederalAudits(),
}));

// Render motion elements as plain elements so whileInView content is visible.
jest.mock('framer-motion', () => ({
  motion: {
    section: ({ children, initial: _i, whileInView: _w, viewport: _v, transition: _t, ...props }: any) => (
      <section {...props}>{children}</section>
    ),
    div: ({ children, initial: _i, animate: _a, whileInView: _w, viewport: _v, transition: _t, ...props }: any) => (
      <div {...props}>{children}</div>
    ),
  },
  useReducedMotion: () => false,
}));

import AuditReportsSection from '@/components/dashboard/AuditReportsSection';

describe('AuditReportsSection with zero publishable findings', () => {
  beforeEach(() => {
    mockUseFederalAudits.mockReturnValue({
      data: GATED_EMPTY_RESPONSE,
      isLoading: false,
      error: null,
    });
  });

  it('does not fabricate a finding count of 1 from an empty severity map', () => {
    render(<AuditReportsSection />);
    // The donut's divide-by-zero guard (`|| 1`) must never surface as a
    // rendered count: the API said 0 findings, the panel may not say 1.
    expect(screen.queryByText('1')).not.toBeInTheDocument();
  });

  it('renders an empty state naming the source and the expected window', () => {
    render(<AuditReportsSection />);
    // What it is waiting for…
    expect(
      screen.getByText(/no findings .* can be published yet/i)
    ).toBeInTheDocument();
    // …why (the withheld count is real data from the response)…
    expect(screen.getByText(/26 findings are held back/)).toBeInTheDocument();
    // …and when the next publication is expected (from next_expected,
    // never a hand-written schedule).
    expect(screen.getByText(/December 2026/)).toBeInTheDocument();
    expect(screen.getByText(/April 2027/)).toBeInTheDocument();
  });

  it('does not render severity legend rows that claim 0/0/0', () => {
    render(<AuditReportsSection />);
    expect(screen.queryByText(/Critical \(0\)/)).not.toBeInTheDocument();
  });

  it('gives the ministries panel an honest empty state', () => {
    render(<AuditReportsSection />);
    expect(screen.getByText(/no ministry can be listed/i)).toBeInTheDocument();
  });
});

describe('AuditReportsSection with published findings', () => {
  it('derives the donut count and the severity breakdown from one map', () => {
    mockUseFederalAudits.mockReturnValue({
      data: {
        ...GATED_EMPTY_RESPONSE,
        total_findings: 2,
        withheld_findings: 0,
        findings_reason: null,
        next_expected: null,
        by_severity: { CRITICAL: 1, WARNING: 1 },
        findings: [
          {
            id: 1,
            entity_name: 'The National Treasury',
            entity_type: 'MINISTRY',
            finding: 'Pending accounts payable of Kshs.20,811,926,257',
            severity: 'WARNING',
            recommended_action: '',
            amount_involved: 'KES 20.8B',
            amount_numeric: 20_811_926_257,
            status: '',
            category: '',
            query_type: '',
            report_section: '',
            date_raised: '',
            date: null,
            title: 'Pending Accounts Payable',
            page_ref: 'p.14',
            source_url: 'https://www.oagkenya.go.ke/wp-content/uploads/2026/05/R.pdf',
          },
          {
            id: 2,
            entity_name: 'Ministry of Health',
            entity_type: 'MINISTRY',
            finding: 'Irregular procurement of KES 12.3 billion',
            severity: 'CRITICAL',
            recommended_action: '',
            amount_involved: 'KES 12.3B',
            amount_numeric: 12_300_000_000,
            status: '',
            category: '',
            query_type: '',
            report_section: '',
            date_raised: '',
            date: null,
          },
        ],
        top_ministries: [
          { ministry: 'Ministry of Health', finding_count: 1 },
          { ministry: 'The National Treasury', finding_count: 1 },
        ],
      },
      isLoading: false,
      error: null,
    });
    render(<AuditReportsSection />);
    expect(screen.getByText('2')).toBeInTheDocument(); // donut count
    expect(screen.getByText(/Critical \(1\)/)).toBeInTheDocument();
    expect(screen.getByText(/Significant \(1\)/)).toBeInTheDocument();
  });

  it('links an expanded finding to the source PDF page a citizen can open', async () => {
    const { fireEvent } = await import('@testing-library/react');
    render(<AuditReportsSection />);
    // Expand the Treasury finding (it carries extraction provenance).
    // shortMinistry() strips the "The " prefix; the name also appears in
    // the ministries panel, so scope to the findings-list button.
    fireEvent.click(
      screen.getByRole('button', { name: /pending accounts payable/i })
    );
    const link = screen.getByRole('link', { name: /source.*p\.14/i });
    expect(link).toHaveAttribute(
      'href',
      'https://www.oagkenya.go.ke/wp-content/uploads/2026/05/R.pdf#page=14'
    );
  });
});
