/**
 * /accountability/unaccounted-funds (formerly /missing-funds) and the county tabs list the findings the
 * Auditor-General's report itself heads "Unaccounted …" or "Loss of Funds"
 * (issue #233). Before, the page read three hand-written county cases that
 * cited nothing, so it was permanently empty; and both county tabs rendered
 * `fmtKES(total_amount)` — which, with the API's honest null total, would
 * have printed a money figure nobody measured.
 */
import '@testing-library/jest-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import type { UnaccountedCase } from '@/types';

// NAROK is one of the eight cases production derives (prod clone, 2026-09-26),
// verbatim. HEADING_ONLY is the shape of a real finding whose body the
// extractor lost (p.39, paragraph 52 has it) — synthetic, not a real case.
const NAROK: UnaccountedCase = {
  finding_id: 2996,
  entity: 'Narok County',
  entity_type: 'county',
  title: 'Unaccounted Expenditure on Transfers to Polytechnics',
  excerpt: 'The statement of receipts and payments reflects an expenditure of Kshs.727,165,8…',
  heading: 'Basis for Adverse Opinion',
  fiscal_year: 'FY2020/21',
  page_ref: 'p.322',
  source: {
    document_id: 2395,
    title: 'REPORT-OF-THE-AUDITOR-GENERAL-FOR-THE-COUNTY-GOVERNMENTS-FOR-THE-YEAR-2020-2021-_VOLUME-I-COUNTY-EXECUTIVES.pdf',
    publisher: 'Office of the Auditor-General',
    url: 'https://www.oagkenya.go.ke/wp-content/uploads/2023/02/VOL-I.pdf',
    page_url: 'https://www.oagkenya.go.ke/wp-content/uploads/2023/02/VOL-I.pdf#page=322',
  },
};
const HEADING_ONLY: UnaccountedCase = {
  finding_id: 1,
  entity: 'Example State Department',
  entity_type: 'ministry',
  title: 'Unaccounted for Motor Vehicles',
  excerpt: '',
  heading: null,
  fiscal_year: 'FY2024/25',
  page_ref: 'p.39',
  source: {
    document_id: 2392,
    title: 'AUDITOR-GENERALS-REPORT-ON-NATIONAL-GOVERNMENT-2024-2025.pdf',
    publisher: 'Office of the Auditor-General',
    url: 'https://www.oagkenya.go.ke/wp-content/uploads/2026/05/NG.pdf',
    page_url: 'https://www.oagkenya.go.ke/wp-content/uploads/2026/05/NG.pdf#page=39',
  },
};

const mockGet = jest.fn();
jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: (...a: unknown[]) => mockGet(...a) } }));
jest.mock('@/components/layout/PageShell', () => ({
  __esModule: true,
  default: ({ title, subtitle, children }: any) => (
    <main>
      <h1>{title}</h1>
      <p>{subtitle}</p>
      {children}
    </main>
  ),
}));

import MissingFundsPage from '@/app/accountability/unaccounted-funds/page';
import UnaccountedFindings from '@/components/accountability/UnaccountedFindings';

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MissingFundsPage />
    </QueryClientProvider>
  );
}

describe('the unaccounted-funds page', () => {
  beforeEach(() => {
    mockGet.mockResolvedValue({
      data: {
        basis: 'oag_finding_title',
        total_amount: null,
        total_amount_reason: 'no_amount_extracted',
        total_cases: 2,
        affected_counties: 1,
        affected_national_entities: 1,
        fiscal_years: ['FY2024/25', 'FY2020/21'],
        cases: [HEADING_ONLY, NAROK],
        reason: null,
        withheld: { count: 0, by_reason: {} },
      },
    });
  });

  it('lists each finding under the report’s own heading, linked to its page', async () => {
    renderPage();
    expect(await screen.findByText('“Unaccounted Expenditure on Transfers to Polytechnics”')).toBeInTheDocument();
    const link = screen.getByRole('link', { name: /report p\.322/ });
    expect(link).toHaveAttribute('href', NAROK.source.page_url);
    expect(screen.getByText('Basis for Adverse Opinion')).toBeInTheDocument();
    expect(screen.getByText(/From the FY2024\/25 and FY2020\/21 reports/)).toBeInTheDocument();
  });

  it('never publishes a money total, and never the word "missing"', async () => {
    renderPage();
    await screen.findByText('“Unaccounted for Motor Vehicles”');
    expect(screen.getByText('Not stated here')).toBeInTheDocument();
    expect(screen.queryByText(/KES\s*\d/)).toBeNull();
    expect(document.body.textContent).not.toMatch(/missing/i);
  });

  it('says so when only the heading was extracted', async () => {
    renderPage();
    await screen.findByText('“Unaccounted for Motor Vehicles”');
    expect(screen.getByText(/Only the heading was extracted/)).toBeInTheDocument();
  });
});

describe('the county-tab list', () => {
  it('renders titles and pages, and no amount', () => {
    render(<UnaccountedFindings cases={[NAROK]} />);
    expect(screen.getByText('“Unaccounted Expenditure on Transfers to Polytechnics”')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /report p\.322/ })).toHaveAttribute('href', NAROK.source.page_url);
    expect(screen.queryByText(/KES/)).toBeNull();
  });

  it('renders nothing when the county has no such finding', () => {
    const { container } = render(<UnaccountedFindings cases={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
