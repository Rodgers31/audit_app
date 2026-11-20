import { fireEvent, render, screen } from '@testing-library/react';
import LoanRegister from '@/app/debt/LoanRegister';
import type { NationalLoansResponse } from '@/lib/api/debt';

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
