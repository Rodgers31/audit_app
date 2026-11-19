import '@testing-library/jest-dom';
import { fireEvent, render, screen } from '@testing-library/react';
import AuditRecurringFindings from '@/app/audits/AuditRecurringFindings';
import { useRecurringFindings } from '@/lib/react-query';

jest.mock('@/lib/react-query', () => ({ useRecurringFindings: jest.fn() }));

const query = jest.mocked(useRecurringFindings);

beforeEach(() => query.mockReset());

it('keeps failed requests distinct from a successful scoped empty response', () => {
  const refetch = jest.fn();
  query.mockReturnValue({ isError: true, refetch } as unknown as ReturnType<typeof useRecurringFindings>);
  const { rerender } = render(<AuditRecurringFindings />);
  expect(screen.getByRole('alert')).toHaveTextContent('Recurring findings could not be loaded.');
  expect(screen.queryByText(/No institution and report section/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
  expect(refetch).toHaveBeenCalledWith({ cancelRefetch: false });

  query.mockReturnValue({
    data: { recurring_findings: [], total: 0, absent_reason: 'No published findings have recorded audit years.' },
  } as unknown as ReturnType<typeof useRecurringFindings>);
  rerender(<AuditRecurringFindings />);
  expect(screen.getByText('No published findings have recorded audit years.')).toBeInTheDocument();
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});

it('announces loading without claiming the collection is empty', () => {
  query.mockReturnValue({ isPending: true } as unknown as ReturnType<typeof useRecurringFindings>);
  render(<AuditRecurringFindings />);
  expect(screen.getByRole('status')).toHaveTextContent('Loading recurring findings…');
  expect(screen.queryByText(/No institution and report section/)).not.toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Browse all findings' })).toHaveAttribute('href', '#audit-findings-heading');
});
