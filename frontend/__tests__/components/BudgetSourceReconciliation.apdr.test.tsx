/**
 * Annual Public Debt Report links come from Treasury's listing (issue #235).
 *
 * The four literal links this component carried all returned 404 on
 * 2026-09-26 — Treasury moved to Drupal — and stopped at FY2025/26.
 */
import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';

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

const mockReports = jest.fn();
jest.mock('@/lib/react-query/useDebt', () => ({
  useAnnualDebtReports: () => mockReports(),
}));

import BudgetSourceReconciliation from '@/components/budget/BudgetSourceReconciliation';

const LISTING = 'https://www.treasury.go.ke/annual-debt-management-reports-0';
const reports = Array.from({ length: 19 }, (_, i) => {
  const y = 2024 - i;
  return {
    fiscal_year: `FY ${y}/${String(y + 1).slice(2)}`,
    title: `Annual Public Debt Report ${y}-${y + 1}`,
    url: `https://www.treasury.go.ke/sites/default/files/Annual-Public-Debt-Report-${y}-${y + 1}.pdf`,
  };
});

describe('BudgetSourceReconciliation — Annual Public Debt Reports', () => {
  it('lists the discovered reports, newest first, and links the full listing', () => {
    mockReports.mockReturnValue({
      data: { status: 'success', listing_url: LISTING, reports },
      isLoading: false,
      isError: false,
    });
    const { container } = render(<BudgetSourceReconciliation />);
    const links = screen.getByTestId('apdr-links').querySelectorAll('a');
    expect(links).toHaveLength(6);
    expect(links[0]).toHaveAttribute('href', reports[0].url);
    expect(screen.getByText('All 19 reports on treasury.go.ke').closest('a')).toHaveAttribute(
      'href',
      LISTING
    );
    expect(container.innerHTML).not.toContain('/wp-content/uploads/');
  });

  it('says the listing is unavailable and still links it — no remembered list', () => {
    mockReports.mockReturnValue({
      data: { status: 'unavailable', listing_url: LISTING, reports: [], reason: 'ConnectError: x' },
      isLoading: false,
      isError: false,
    });
    const { container } = render(<BudgetSourceReconciliation />);
    expect(screen.getByTestId('apdr-unavailable')).toBeInTheDocument();
    expect(container.querySelectorAll('a[href$=".pdf"]')).toHaveLength(0);
    expect(
      screen.getByText('Treasury’s list of Annual Public Debt Reports').closest('a')
    ).toHaveAttribute('href', LISTING);
  });
});
