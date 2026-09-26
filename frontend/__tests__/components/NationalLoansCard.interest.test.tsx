/**
 * The homepage loans card, rendered from the /debt/loans payload (issue #235).
 *
 * On production 2026-09-26 this card listed its fourteen smallest rows, every
 * one reading "0.00%  KES 0", under an "Annual Service Cost" of KES 1.02T —
 * three April-2025 fixture rates times three balances. Rows are now absent
 * ("—") unless a publisher gives the figure, and the headline is the current
 * fiscal year's published debt service.
 */
import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';
import type { NationalLoansResponse } from '@/lib/api/debt';

const absent = {
  interest_rate: null,
  interest_rate_pct: null,
  interest_rate_basis: null,
  interest_rate_label: null,
  interest_rate_source: null,
  interest_rate_absent_reason: 'World Bank IDS reports the interest Kenya paid this creditor, not the interest rate on the loans.',
  annual_service_cost: null,
  annual_service_basis: null,
  annual_service_label: null,
  annual_service_source: null,
  annual_service_absent_reason: 'World Bank IDS publishes no interest-paid figure for this creditor for 2024.',
};

const row = (lender: string, amount: number) => ({
  lender,
  lender_type: 'external_bilateral',
  principal: String(amount),
  outstanding: String(amount),
  outstanding_numeric: amount,
  principal_numeric: amount,
  issue_date: '2024-12-31',
  maturity_date: '',
  status: null,
  ...absent,
});

const PAYLOAD: NationalLoansResponse = {
  loans: [
    row('Bilateral (Finland)', 0.2e9),
    {
      ...row('Bilateral (China)', 723.6e9),
      annual_service_cost: 45.0e9,
      annual_service_basis: 'published',
      annual_service_label: 'Interest paid in 2024',
      annual_service_absent_reason: null,
    },
  ],
  total_loans: 2,
  total_outstanding: 723.8e9,
  total_annual_service_cost: null,
  annual_debt_service: {
    value_kes: 2_315_900_000_000,
    fiscal_year: 'FY 2026/27',
    measure: 'Total debt service: interest plus principal redemptions, domestic and external',
    source: {
      publisher: 'The National Treasury',
      title: 'Programme Based Budget FY 2026/27 (Approved)',
      url: 'https://www.treasury.go.ke/x.pdf',
      page: 'CFS summary PDF p.1193',
    },
    absent_reason: null,
  },
  source: 'World Bank IDS',
  source_url: 'https://api.worldbank.org/',
};

// framer-motion's whileInView needs IntersectionObserver, which jsdom lacks.
jest.mock('framer-motion', () => ({
  motion: new Proxy(
    {},
    {
      get:
        () =>
        ({ children, initial, animate, whileInView, viewport, transition, exit, ...props }: any) => (
          <div {...props}>{children}</div>
        ),
    }
  ),
  AnimatePresence: ({ children }: any) => <>{children}</>,
}));

const mockLoans = jest.fn();
jest.mock('@/lib/react-query/useDebt', () => ({
  useNationalLoans: () => mockLoans(),
}));
jest.mock('@/lib/i18n/LangProvider', () => ({
  useLang: () => ({ t: (k: string) => k, lang: 'en' }),
}));
jest.mock('@/components/dashboard/DebtExplainerModal', () => () => null);

import NationalLoansCard from '@/components/dashboard/NationalLoansCard';

describe('NationalLoansCard', () => {
  beforeEach(() => mockLoans.mockReturnValue({ data: PAYLOAD, isLoading: false, error: null }));

  it('headlines the published debt service, with its year and document', () => {
    render(<NationalLoansCard />);
    const figure = screen.getByTestId('loans-annual-debt-service');
    expect(figure).toHaveTextContent('2.32T');
    expect(figure.getAttribute('title')).toContain('CFS summary PDF p.1193');
    expect(
      screen.getByText('FY 2026/27 · Programme Based Budget FY 2026/27 (Approved)')
    ).toBeInTheDocument();
  });

  it('never prints a manufactured 0.00% or KES 0', () => {
    const { container } = render(<NationalLoansCard />);
    expect(container.textContent).not.toMatch(/0\.00%/);
    expect(container.textContent).not.toMatch(/KES 0(?![.\d])/);
  });

  it('an absent figure is a dash that says why', () => {
    render(<NationalLoansCard />);
    const dash = screen
      .getAllByText('—')
      .find((el) => el.getAttribute('title')?.startsWith('World Bank IDS reports the interest'));
    expect(dash).toBeDefined();
  });

  it('names the creditor, not just its class', () => {
    render(<NationalLoansCard />);
    expect(screen.getByText('Finland')).toBeInTheDocument();
    expect(screen.getByText('China')).toBeInTheDocument();
  });
});
