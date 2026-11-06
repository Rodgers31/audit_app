import { render, screen } from '@testing-library/react';
import FiscalMeasureDisclosure from '@/components/budget/FiscalMeasureDisclosure';
import BudgetFlowHero from '@/components/budget/BudgetFlowHero';

jest.mock('framer-motion', () => ({ motion: new Proxy({}, { get: () => ({ children, initial, animate, whileInView, viewport, transition, ...props }: any) => <div {...props}>{children}</div> }) }));

test('withheld revenue and debt service are explained without invented zero', () => {
  render(<FiscalMeasureDisclosure absentReasons={{ total_revenue: 'measure_source_unconfirmed', debt_service_cost: 'measure_source_unconfirmed' }} />);
  expect(screen.getByText(/Ordinary revenue, excluding A-i-A and grants: withheld/)).toBeInTheDocument();
  expect(screen.getByText(/Debt service, interest and principal: withheld/)).toBeInTheDocument();
  expect(screen.queryByText(/KES 0/)).not.toBeInTheDocument();
});

test('qualified positive control shows the source, vintage and printed precision', () => {
  render(<FiscalMeasureDisclosure qualifications={{ total_revenue: {
    value_kes: 2041119000000, fiscal_year: 'FY 2022/23', basis: 'ordinary_revenue_excl_aia',
    vintage: 'Preliminary', precision_kes: 1000000,
    source: { title: 'APDMR September 2023', url: 'https://www.treasury.go.ke/source.pdf', page: 'Table 4.1-1, PDF p.37', sha256: 'a'.repeat(64) },
  } }} />);
  expect(screen.getByText(/Preliminary; printed precision KES 1,000,000/)).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /APDMR September 2023/ })).toHaveAttribute('href', 'https://www.treasury.go.ke/source.pdf');
});

test('hero preserves a withheld ratio even when raw numerator and denominator exist', () => {
  const { container } = render(<BudgetFlowHero data={{ fiscal_year: 'FY 2022/23', total_revenue: 2041.119, debt_service_cost: 1201.033, debt_service_per_shilling: null }} />);
  expect(container.textContent).not.toContain('58.8');
  expect(container.textContent).not.toMatch(/KES\s+59/);
  expect(container.textContent).toContain('compatible source evidence unconfirmed');
  expect(container.textContent).toContain('Approved budget for FY 2022/23 withheld');
});


test('debt chart and headline retain an explicitly withheld server ratio', () => {
  const { buildDebtServiceSeries } = require('@/lib/debt/debtServiceSeries');
  const { computeRevenueAllocation } = require('@/lib/debt/revenueAllocation');
  const row = { fiscal_year: 'FY 2026/27', debt_service_cost: 2315.9, total_revenue: 2985.7, debt_service_per_shilling: null };
  expect(buildDebtServiceSeries([row])[0].ratio).toBeNull();
  expect(computeRevenueAllocation(row)).toBeNull();
});
