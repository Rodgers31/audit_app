import '@testing-library/jest-dom';
import { render, screen, waitFor } from '@testing-library/react';
import type { FederalAuditHeadline, FederalAuditResponse } from '@/lib/api/audits';
import { LangProvider } from '@/lib/i18n/LangProvider';

// The exact shape /api/v1/audits/federal returns when the publication gate
// withholds every federal finding (verified against the live DB 2026-08-29:
// 26 ministry/national rows withheld, 0 published).
const GATED_EMPTY_RESPONSE = {
  report_title: null,
  auditor_general: 'Office of the Auditor General of Kenya',
  fiscal_year: null,
  report_date: null,
  total_findings: 0,
  total_amount_questioned: null,
  total_amount_questioned_reason: 'not_extracted',
  withheld_findings: 26,
  findings_with_amount: 0,
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
  headline: null,
  headline_reason: 'no_extraction_backed_findings',
  findings: [],
  top_ministries: [],
  last_updated: null,
} satisfies FederalAuditResponse;

const mockUseFederalAudits = jest.fn();
jest.mock('@/lib/react-query/useAudits', () => ({
  ...jest.requireActual('@/lib/react-query/useAudits'),
  useFederalAuditsHomeSummary: () => mockUseFederalAudits(),
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

describe('AuditReportsSection withholding reasons (#366 integration)', () => {
  const reasons = {
    source_document_has_no_url: 1,
    source_document_has_invalid_url: 2,
    finding_text_unreadable_cid: 3,
    no_page_reference: 4,
    future_gate_reason: 5,
    toString: 6,
    zero_reason: 0,
  };

  it.each([
    ['en', /2 finding\(s\) held back because the source document link is invalid or unsafe/i,
      /4 finding\(s\) held back because the page reference is missing or invalid/i,
      /5 finding\(s\) held back because another publication check did not pass/i],
    ['sw', /Matokeo 2 yamezuiliwa kwa sababu kiungo cha hati ya chanzo si sahihi au si salama/i,
      /Matokeo 4 yamezuiliwa kwa sababu rejeleo la ukurasa halipo au si sahihi/i,
      /Matokeo 5 yamezuiliwa kwa sababu hayakupita ukaguzi mwingine wa uchapishaji/i],
    ['plain', /2 finding\(s\) held back because the report link does not work safely/i,
      /4 finding\(s\) held back because they do not give a usable page reference/i,
      /5 finding\(s\) held back because another check was not met/i],
  ] as const)('renders known and unknown positive reasons in %s, omitting zero', async (language, invalidUrl, invalidPage, unknown) => {
    localStorage.setItem('auditgava-lang', language);
    mockUseFederalAudits.mockReturnValue({ data: {
      ...GATED_EMPTY_RESPONSE, withheld_findings: 21, withheld_findings_by_reason: reasons,
    }, isLoading: false, error: null });
    render(<LangProvider><AuditReportsSection /></LangProvider>);
    await waitFor(() => expect(screen.getAllByText(invalidUrl).length).toBeGreaterThan(0));
    expect(screen.getAllByText(invalidPage).length).toBeGreaterThan(0);
    expect(screen.getAllByText(unknown).length).toBeGreaterThan(0);
    expect(screen.getAllByText(new RegExp(unknown.source.replace('5', '6'), 'i')).length).toBeGreaterThan(0);
    expect(screen.queryByText(/0 finding\(s\) held back|Matokeo 0 yamezuiliwa/i)).toBeNull();
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
            source_url: 'https://www.oagkenya.go.ke/wp-content/uploads/2026/05/R.pdf#zoom=100',
            source_page_url: 'https://www.oagkenya.go.ke/wp-content/uploads/2026/05/R.pdf#zoom=100&page=14',
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
      'https://www.oagkenya.go.ke/wp-content/uploads/2026/05/R.pdf#zoom=100&page=14'
    );
  });

  describe('the partial questioned amount', () => {
    // Production FY2024/25: the Auditor-General's own questioned total is not
    // in the report's machine-readable section, so the "Amount Questioned"
    // tile shows an em-dash. 49 of 813 findings do state a figure, summing to
    // KES 73.4B. Hiding that publishes less than we know; showing it bare
    // would imply it is the report's headline. It is shown WITH its coverage.
    const withPartial = {
      ...GATED_EMPTY_RESPONSE,
      total_findings: 813,
      findings: [],
      total_amount_questioned: null,
      total_amount_in_findings: 73_382_064_434,
      findings_with_amount: 49,
    };

    it('states the sum together with how many findings it covers', () => {
      mockUseFederalAudits.mockReturnValue({
        data: withPartial, isLoading: false, error: null,
      });
      render(<AuditReportsSection />);
      expect(screen.getByText(/across 49 of 813 findings/i)).toBeInTheDocument();
      expect(
        screen.getByText(/not the report.s headline figure/i)
      ).toBeInTheDocument();
    });

    it('stays hidden when the Auditor-General\'s own total IS available', () => {
      // Two competing money figures side by side would be worse than one.
      mockUseFederalAudits.mockReturnValue({
        data: { ...withPartial, total_amount_questioned: 981_300_000_000 },
        isLoading: false, error: null,
      });
      render(<AuditReportsSection />);
      expect(screen.queryByText(/across 49 of 813 findings/i)).toBeNull();
    });

    it('stays hidden when no finding states a figure', () => {
      mockUseFederalAudits.mockReturnValue({
        data: { ...withPartial, total_amount_in_findings: null, findings_with_amount: 0 },
        isLoading: false, error: null,
      });
      render(<AuditReportsSection />);
      expect(screen.queryByText(/across .* findings/i)).toBeNull();
    });
  });
});

// The headline production's FY2024/25 report derives, measured on a clone of
// the production database taken 2026-09-26 (issue #233), after excluding the
// 304 prior-year table rows the extractor reads as findings. Typed, so `tsc`
// fails the moment the hand-written interface drifts from the payload.
const LIVE_HEADLINE: FederalAuditHeadline = {
  basis: 'extracted_section_headings',
  source_document: {
    id: 2392,
    title: 'AUDITOR-GENERALS-REPORT-ON-NATIONAL-GOVERNMENT-2024-2025.pdf',
    url: 'https://www.oagkenya.go.ke/wp-content/uploads/2026/05/AUDITOR-GENERALS-REPORT-ON-NATIONAL-GOVERNMENT-2024-2025.pdf',
  },
  entities_with_findings: 37,
  excluded_table_rows: 304,
  entities_opinion_read: 23,
  modified_opinions: [
    { opinion: 'Disclaimer', entities: 1, findings: 8 },
    { opinion: 'Qualified', entities: 8, findings: 45 },
  ],
  entities: [
    {
      entity: 'State Department for Medical Services',
      opinion: 'Disclaimer',
      findings: 8,
      page_ref: 'p.295',
      source_url:
        'https://www.oagkenya.go.ke/wp-content/uploads/2026/05/AUDITOR-GENERALS-REPORT-ON-NATIONAL-GOVERNMENT-2024-2025.pdf#page=295',
    },
    {
      entity: 'The National Treasury',
      opinion: 'Qualified',
      findings: 3,
      page_ref: 'p.21',
      source_url:
        'https://www.oagkenya.go.ke/wp-content/uploads/2026/05/AUDITOR-GENERALS-REPORT-ON-NATIONAL-GOVERNMENT-2024-2025.pdf#page=21',
    },
  ],
  recurring_prior_year: {
    entities: 17,
    findings: 36,
    page_ref: 'p.14',
    source_url:
      'https://www.oagkenya.go.ke/wp-content/uploads/2026/05/AUDITOR-GENERALS-REPORT-ON-NATIONAL-GOVERNMENT-2024-2025.pdf#page=14',
  },
  emphasis_of_matter: {
    entities: 15,
    findings: 76,
    most_common_title: 'Budgetary Control and Performance',
    most_common_findings: 41,
    page_ref: 'p.14',
    source_url:
      'https://www.oagkenya.go.ke/wp-content/uploads/2026/05/AUDITOR-GENERALS-REPORT-ON-NATIONAL-GOVERNMENT-2024-2025.pdf#page=14',
  },
};

describe('AuditReportsSection with a derived headline (issue #233)', () => {
  const withHeadline = {
    ...GATED_EMPTY_RESPONSE,
    fiscal_year: 'FY2024/25',
    total_findings: 813,
    withheld_findings: 26,
    withheld_findings_by_reason: {
      source_document_has_no_url: 25,
      finding_text_unreadable_cid: 1,
      no_page_reference: 0,
    },
    headline: LIVE_HEADLINE,
    headline_reason: null,
    findings_reason: null,
    next_expected: null,
    by_severity: { WARNING: 1 },
    findings: [
      {
        id: 2419,
        entity_name: 'The National Treasury',
        entity_type: 'MINISTRY',
        finding: 'Unsupported Payments The statement reflects payments not supported by documents.',
        severity: 'WARNING',
        recommended_action: '',
        amount_involved: '',
        amount_numeric: null,
        status: 'published_report',
        category: '',
        query_type: 'REPORT ON THE FINANCIAL STATEMENTS',
        report_section: '',
        date_raised: '',
        date: null,
        page_ref: 'p.21',
      },
    ],
  } satisfies FederalAuditResponse;

  beforeEach(() => {
    mockUseFederalAudits.mockReturnValue({ data: withHeadline, isLoading: false, error: null });
  });

  it('replaces "not yet published" with the opinions the report states', () => {
    render(<AuditReportsSection />);
    expect(screen.queryByText(/audit opinion not yet published here/i)).toBeNull();
    expect(screen.getByText(/modified audit opinions found in this report/i)).toBeInTheDocument();
    expect(screen.getByText('1 vote(s) · 8 finding(s)')).toBeInTheDocument();
    expect(screen.getByText('8 vote(s) · 45 finding(s)')).toBeInTheDocument();
  });

  it('links every vote it names to the page the opinion was found on', () => {
    render(<AuditReportsSection />);
    const link = screen.getByRole('link', { name: /p\.295/ });
    expect(link).toHaveAttribute('href', LIVE_HEADLINE.entities[0].source_url);
  });

  it('states what the counts were read from, so they cannot pass as totals', () => {
    render(<AuditReportsSection />);
    expect(screen.getByText(/could be read for 23 of the 37 votes/)).toBeInTheDocument();
    expect(screen.getByText(/these counts are minimums/)).toBeInTheDocument();
    expect(screen.getByText(/No vote is shown as clean/)).toBeInTheDocument();
  });

  it('fills the tiles that used to be em-dashes from the derived counts', () => {
    render(<AuditReportsSection />);
    expect(screen.getByText('37')).toBeInTheDocument(); // votes with extracted findings
    expect(screen.getByText('17')).toBeInTheDocument(); // unresolved prior-year
    expect(screen.getByRole('link', { name: 'votes' })).toHaveAttribute(
      'href',
      LIVE_HEADLINE.recurring_prior_year!.source_url
    );
  });

  it('gives each withheld finding its own reason', () => {
    // Production rendered "26 findings held back for lack of a traceable
    // source document" — true of 25 of them. The 26th is unreadable text.
    render(<AuditReportsSection />);
    expect(screen.getByText(/25 finding\(s\) held back for lack of a traceable source document/)).toBeInTheDocument();
    expect(screen.getByText(/1 finding\(s\) held back because the extracted text is unreadable/)).toBeInTheDocument();
    expect(screen.queryByText(/26 finding/)).toBeNull();
    expect(screen.queryByText(/0 finding/)).toBeNull();
  });

  it('also shows a new URL reason beside a published finding', () => {
    mockUseFederalAudits.mockReturnValue({ data: {
      ...withHeadline,
      withheld_findings: 2,
      withheld_findings_by_reason: { source_document_has_invalid_url: 2 },
    }, isLoading: false, error: null });
    render(<AuditReportsSection />);
    expect(screen.getByText(/2 finding\(s\) held back because the source document link is invalid or unsafe/)).toBeInTheDocument();
  });

  it('summarises Emphasis of Matter in the report\'s words, with its page', () => {
    render(<AuditReportsSection />);
    expect(screen.getByText(/Raised on 15 votes \(76 paragraphs\)/)).toBeInTheDocument();
    expect(screen.getByText(/Budgetary Control and Performance/)).toBeInTheDocument();
  });

  it('says none was found, with its coverage, rather than inventing a clean opinion', () => {
    mockUseFederalAudits.mockReturnValue({
      data: { ...withHeadline, headline: { ...LIVE_HEADLINE, modified_opinions: [], entities: [] } },
      isLoading: false,
      error: null,
    });
    render(<AuditReportsSection />);
    expect(screen.getByText(/No .Basis for … Opinion. section was found among the 23 votes/)).toBeInTheDocument();
    expect(screen.queryByText(/clean opinion/i)).toBeNull();
  });
});
