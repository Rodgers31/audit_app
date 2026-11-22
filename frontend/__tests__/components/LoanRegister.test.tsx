import { fireEvent, render, screen } from '@testing-library/react';
import LoanRegister from '@/app/debt/LoanRegister';
import type { NationalLoan, NationalLoansResponse } from '@/lib/api/debt';

let mockSearchParams = new URLSearchParams();
jest.mock('next/navigation', () => ({ useSearchParams: () => mockSearchParams }));

describe('LoanRegister request states', () => {
  it('distinguishes first load, first error, fetching a retry and a successful empty list', () => {
    const retry = jest.fn();
    const { rerender } = render(
      <LoanRegister data={undefined} isLoading isError={false} isFetching retry={retry} />
    );
    expect(screen.getByRole('status')).toHaveTextContent('Loading the loan register');
    expect(screen.queryByText('No loan register records are available.')).toBeNull();

    rerender(<LoanRegister data={undefined} isLoading={false} isError isFetching={false} retry={retry} />);
    expect(screen.getByRole('alert')).toHaveTextContent('The loan register could not be loaded.');
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(retry).toHaveBeenCalledTimes(1);

    rerender(<LoanRegister data={undefined} isLoading={false} isError isFetching retry={retry} />);
    expect(screen.getByRole('button', { name: 'Loading the loan register…' })).toBeDisabled();

    const data: NationalLoansResponse = {
      loans: [], total_loans: 0, total_outstanding: null, total_annual_service_cost: null,
      annual_debt_service: { value_kes: null, absent_reason: null }, source: '', source_url: '',
    };
    rerender(<LoanRegister data={data} isLoading={false} isError={false} isFetching={false} retry={retry} />);
    expect(screen.getByText('No loan register records are available.')).toBeVisible();
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.queryByRole('searchbox')).toBeNull();
  });
});

test('uses a single validated lender query and preserves manual edits and sort across navigation', () => {
  const lender = 'Synthetic Window (Water & Energy)';
  const other = 'Different Fixture Lender';
  const loans = [lender, other].map(name => ({
    lender: name, lender_type: 'external_multilateral', outstanding_numeric: 1,
  }) as NationalLoan);
  const data: NationalLoansResponse = {
    loans, total_loans: 2, total_outstanding: null, total_annual_service_cost: null,
    annual_debt_service: { value_kes: null, absent_reason: null }, source: '', source_url: '',
  };
  const element = () => <LoanRegister data={data} isLoading={false} isError={false} isFetching={false} retry={jest.fn()} />;
  mockSearchParams = new URLSearchParams({ lender });
  const { rerender } = render(element());
  const input = screen.getByRole('searchbox');
  const sort = screen.getByRole('combobox');
  expect(input).toHaveValue(lender);
  expect(screen.queryByText(other, { exact: true })).not.toBeInTheDocument();

  fireEvent.change(input, { target: { value: 'different' } });
  fireEvent.change(sort, { target: { value: 'rate' } });
  rerender(element());
  expect(input).toHaveValue('different');
  expect(screen.queryByText(lender, { exact: true })).not.toBeInTheDocument();

  mockSearchParams = new URLSearchParams({ lender: other });
  rerender(element());
  expect(input).toHaveValue(other);
  expect(sort).toHaveValue('rate');

  for (const query of ['lender=one&lender=two', 'lender=%0Atest', `lender=${'x'.repeat(201)}`]) {
    mockSearchParams = new URLSearchParams(query);
    rerender(element());
    expect(input).toHaveValue('');
  }
  mockSearchParams = new URLSearchParams();
});
